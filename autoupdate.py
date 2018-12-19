#!/usr/bin/env python3

import botocore
import boto3
from datetime import datetime
import urllib3
import json
import time
from pprint import pprint

ec2 = boto3.client('ec2', region_name='us-east-1')

elb = boto3.client('elb', region_name='us-east-1')


#### This block gets the security group ID's of the existing SGs ####
def get_existing_SGs():
    old_ids = {}
    info = []
    sg_to_remove = []
    sg_to_keep = []

    jira_elb = elb.describe_load_balancers(
    LoadBalancerNames=['Bitbucket-external-ELB',])

    lblist = jira_elb['LoadBalancerDescriptions'][0]['SecurityGroups']
    for item in lblist:
        info.append(ec2.describe_security_groups(
            GroupIds=[item]
            ))
    for i in range(0,len(info)):
        old_ids[info[i]['SecurityGroups'][0]['GroupName']] = info[i]['SecurityGroups'][0]['GroupId']
    keylst = list(old_ids.keys())
    for z in keylst:
        if 'jira' in z:
            sg_to_remove.append(old_ids[z])
        else:
            sg_to_keep.append(old_ids[z])
    return (sg_to_remove, sg_to_keep)
        
##### Get cidr list of existing SG ######
def get_existing_whitelist(sg):
    existing_whitelist = []

    response = ec2.describe_security_groups(
        GroupIds=sg)
    for i in response['SecurityGroups'][0]['IpPermissions'][0]['IpRanges']:
        existing_whitelist.append(i['CidrIp'])
    for i in response['SecurityGroups'][0]['IpPermissions'][0]['Ipv6Ranges']:
        existing_whitelist.append(i['CidrIpv6'])
    return existing_whitelist


### This gets the whitelist from https://ip-ranges.atlassian.com
def get_new_whitelist():
    whitelist = []
    urllib3.disable_warnings()
    http = urllib3.PoolManager()
    v = http.request('GET', 'http://ip-ranges.atlassian.com/',)
    raw_list = json.loads(v.data)
    for ip in range(0,len(raw_list["items"])):
        whitelist.append(raw_list["items"][ip]['cidr'])
    return whitelist

### Split lists for ipv4 and ipv6 addresses
def split_lists(whitelist):
    ipv4 = []
    ipv6 = []
    for i in whitelist:
        if ':' in i:
            ipv6.append(i)
        else:
            ipv4.append(i)
    return (ipv4, ipv6)

#### create new SG and add whitelisted IPs
def create_new_sg(ipv4, ipv6, old_sg):
    timestamp = str(datetime.utcnow().strftime('%Y-%m-%d-%H:%M:%S'))

    # pprint(old_sg)
    old_sg_info = ec2.describe_security_groups(GroupIds=old_sg)
    # pprint(old_sg_info)

    secGroup = ec2.create_security_group(
        GroupName=f'jira.cloud_{timestamp}', Description='JiraCloud Ingress IPs', VpcId=old_sg_info['SecurityGroups'][0]['VpcId'])
    for i in ipv4:
        ec2.authorize_security_group_ingress(
            CidrIp=i,
            IpProtocol='tcp',
            FromPort=443,
            GroupId=secGroup['GroupId'],
            ToPort=443
        )
    for i in ipv6:
        ec2.authorize_security_group_ingress(
            GroupId=secGroup['GroupId'],
            IpPermissions=[
                {
                    'FromPort' : 443,
                    'IpProtocol' : 'tcp',
                    'Ipv6Ranges' : [
                        {
                            'CidrIpv6' : i,
                        }
                    ],
                    'ToPort' : 443
                },
            ]
        )
    return secGroup['GroupId']


if __name__ == "__main__":
    sg_to_remove, sg_to_keep = get_existing_SGs()

    print('Currently Attached SGs:', sg_to_remove, sg_to_keep)
    existing_sg = sg_to_remove[0]

    existing_whitelist = get_existing_whitelist(sg_to_remove)

    whitelist = get_new_whitelist()
    ###Compare whitelists
    diff = set(whitelist) - set(existing_whitelist)
    if diff == set():
        print("No differences between current list and  Atlassian list, Exiting")
        exit(0)
    ipv4, ipv6 = split_lists(whitelist)

    if diff != {}:
        print("lists are different; updating")
        new_sg_id = create_new_sg(ipv4, ipv6, sg_to_remove)
        print(f'The new SG ID is {new_sg_id}')

        #### Apply the offices and the new whitelist SG to the ELB
        print('removing',[sg_to_remove], 'from load balancer and keeping', sg_to_keep)
        elb.apply_security_groups_to_load_balancer(
            LoadBalancerName='Bitbucket-external-ELB',
            SecurityGroups=[new_sg_id] + sg_to_keep)

        #### Delete the old SG from AWS
        print('Attachment Successful, deleting', sg_to_remove)
        time.sleep(5)
        ec2.delete_security_group(
            GroupId=existing_sg)
        print('Update finished, you now have the latest Atlassian IP range Installed')
             

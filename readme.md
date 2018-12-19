# Atlassian Auto-Updater

## This script grabs the ips from http://ip-ranges.atlassian.com, and compares them to the IPs allowed in our security group for allowing jiraCloud integration with Bitbucket.

The basics are the following

Pull the security groups attached to the LB
Get the list of allowed ips
Pull the list from Atlassian
compare If the same, do nothing
if different 
# dpdk-tools

A collection of scripts that make determing DPDK-related configurations
for OpenStack-Ansible a little easier.

Example input:

```
##########
# The following are tunables used to build the masks for Open vSwitch
#
# os_cores_per_node defines the number of cores to reserve (per node) for OS
# housekeeping duties. The sibling thread will also be reserved.
os_cores_per_node = 1
#
# pmd_cores_per_node defines the number of cores to reserve (per node) for
# DPDK poll mode drivers. The sibling thread will also be reserved.
pmd_cores_per_node = 1
#
# host_memory_per_node is the amount of memory to reserve for DPDK (per node).
# Recommendations are 1024 (MB) for 1500 MTU and 4096 (MB) for 9000 MTU.
host_memory_per_node = 4096
##########
```

Example output:

```
The following table provides the breakdown of cores/threads per numa node
reserved for their respective function.
+----------------+-----------------------+---------+---------------------------------------+---------------------------------+
| Reserved Cores |        Purpose        |   Mask  |                 node1                 |              node0              |
+----------------+-----------------------+---------+---------------------------------------+---------------------------------+
|  [0,8,16,24]   | Host Operating System | 1010101 |                 [8,24]                |              [0,16]             |
|  [1,9,17,25]   |       DPDK PMDs       | 2020202 |                 [9,25]                |              [1,17]             |
|      N/A       |    Virtual Machines   |   None  | [10,11,12,13,14,15,26,27,28,29,30,31] | [2,3,4,5,6,7,18,19,20,21,22,23] |
+----------------+-----------------------+---------+---------------------------------------+---------------------------------+

Recommended kernel parameters:
"GRUB_CMDLINE_LINUX="... isolcpus=1-7,9-15,17-23,25-31 nohz_full=1-7,9-15,17-23,25-31 rcu_nocbs=1-7,9-15,17-23,25-31

Overrides:
ovs_dpdk_lcore_mask: 1010101
ovs_dpdk_pmd_cpu_mask: 2020202
ovs_dpdk_pci_addresses: TBD
ovs_dpdk_socket_mem: 4096,4096
```

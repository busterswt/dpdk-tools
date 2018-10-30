#!/usr/bin/python
# James Denton <james.denton@rackspace.com>
# Hex conversions provided by https://access.redhat.com/solutions/3221381

import os,re
import json
import glob
import itertools
from prettytable import PrettyTable

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

cpuinfo = '/proc/cpuinfo'
cputopology = '/sys/devices/system/cpu'
nodetopology = '/sys/devices/system/node'

class bcolors:
   OKGREEN = '\033[92m'
   FAIL = '\033[91m'
   ENDC = '\033[0m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'

def listToRanges(intList):
    ret = []
    for val in sorted(intList):
        if not ret or ret[-1][-1]+1 != val:
            ret.append([val])
        else:
            ret[-1].append(val)
    return ",".join([str(x[0]) if len(x)==1 else str(x[0])+"-"+str(x[-1]) for x in ret])

def siblings(cputopology, cpudir, siblingsfile):
    # Known core_siblings_list / thread_siblings_list  formats:
    ## 0
    ## 0-3
    ## 0,4,8,12
    ## 0-7,64-71
    value = file('/'.join([cputopology, cpudir, 'topology', siblingsfile])).read().rstrip('\n')
    siblingslist = []
    for item in value.split(','):
        if '-' in item:
           subvalue = item.split('-')
           siblingslist.extend(range(int(subvalue[0]), int(subvalue[1]) + 1))
        else:
           siblingslist.extend([int(item)])
    return siblingslist

def get_node_cores(node):
    # Function returns a list of cores/threads for a given node
    value = file('/'.join([nodetopology, node, '/cpulist'])).read().rstrip('\n')
    corelist = []

    for item in value.split(','):
        if '-' in item:
            subvalue = item.split('-')
            corelist.extend(range(int(subvalue[0]), int(subvalue[1]) + 1))
        else:
            corelist.extend([int(item)])
    return corelist

def get_core_siblings(topology,cores):
    # Function returns sibling pairs for given core(s)
    _siblings = []
    for core in cores:
        _siblings.append(topology['cpus']['cpu'+str(core)]['thread_siblings_list'])
    return list(itertools.chain(*_siblings))

def get_host_reserved_cores(topology):
    # Function returns recommend core/thread pairs
    # for host reservation
    _os_cores = []
    os_cores = []
    for node in topology['nodes']:
        # os_cores are selected from the front of the list
        cpulist = sorted(topology['nodes'][node]['cpulist'])
        i = 0
        while i < os_cores_per_node:
            _os_cores.append(cpulist[0])
            siblings = get_core_siblings(topology,[cpulist[0]])
            cpulist = list(set(cpulist) - set(siblings))
            i += 1
        topology['nodes'][node]['cpulist'] = cpulist
        topology['nodes'][node]['os_cores'] = get_core_siblings(topology,_os_cores[:])
        os_cores.append(topology['nodes'][node]['os_cores'])
        del _os_cores[:]
    return list(itertools.chain(*os_cores))

def get_pmd_reserved_cores(topology):
    # Function returns recommend core/thread pairs
    # for pmd reservation
    _pmd_cores = []
    pmd_cores = []
    for node in topology['nodes']:
        # os_cores have been popped. pmd_cores come from the front now.
        cpulist = sorted(topology['nodes'][node]['cpulist'])
        i = 0
        while i < pmd_cores_per_node:
            _pmd_cores.append(cpulist[0])
            siblings = get_core_siblings(topology,[cpulist[0]])
            cpulist = list(set(cpulist) - set(siblings))
            i += 1
        topology['nodes'][node]['cpulist'] = cpulist
        topology['nodes'][node]['pmd_cores'] = get_core_siblings(topology,_pmd_cores[:])
        pmd_cores.append(topology['nodes'][node]['pmd_cores'])
        del _pmd_cores[:]
    return list(itertools.chain(*pmd_cores))

def get_host_mask(cpulist):
    # Function returns hexadecimal mask for host core reservation
    cpus = ','.join(str(e) for e in cpulist)
    cpu_arr = cpus.split(",")
    binary_mask = 0
    for cpu in cpu_arr:
        binary_mask = binary_mask | (1 << int(cpu))
    return format(binary_mask, '02x')

def main():

    topology = {}
    topology['cpus'] = {}
    topology['nodes'] = {}
    topology['host_cores'] = []
    topology['os_cores'] = []
    topology['pmd_cores'] = []

    # Construct numa node topology
    try:
        r = re.compile('^node[0-9]+')
        nodes = [f for f in os.listdir(nodetopology) if r.match(f)]
        for node in nodes:
            n = {}
            topology['nodes'][node] = n
            n['cpulist'] = get_node_cores(node)
            topology['host_cores'].extend(get_node_cores(node))
    except:
        topology = {"error": "Error constructing node topology"}

    # Construct cpu topology
    try:
        r = re.compile('^cpu[0-9]+')
        cpudirs = [f for f in os.listdir(cputopology) if r.match(f)]
        for cpudir in cpudirs:
            t = {}
            topology['cpus'][cpudir] = t
            t['physical_package_id'] = file('/'.join([cputopology, cpudir, '/topology/physical_package_id'])).read().rstrip('\n')
            t['numa_node'] = os.path.basename(glob.glob('/'.join([cputopology, cpudir, '/node*']))[0])[-1:]
            t['core_siblings_list'] = siblings(cputopology, cpudir, 'core_siblings_list')
            t['thread_siblings_list'] = siblings(cputopology, cpudir, 'thread_siblings_list')

    except:
        # Cleaning the topology due to error.
        # /proc/cpuinfo will be used instead.
        topology = {"error": "Error accessing /sys. Use /proc/cpuinfo."}

    # Build masks based on coded values
    topology['os_cores'] = get_host_reserved_cores(topology)
    topology['pmd_cores'] = get_pmd_reserved_cores(topology)
    topology['host_mask'] = get_host_mask(topology['os_cores'])
    topology['pmd_mask'] = get_host_mask(topology['pmd_cores'])

    # Generate table
    cpuTable = PrettyTable()
    # Generate field names
    fields = ["Reserved Cores", "Purpose", "Mask"]
    for node in topology['nodes']:
        fields.append(node)
    cpuTable.field_names = fields

    # Host reservation
    row = [str(sorted(topology['os_cores'])).replace(" ",""),"Host Operating System",
           bcolors.OKGREEN + topology['host_mask'] + bcolors.ENDC]
    for node in topology['nodes']:
        row.append(str(sorted(topology['nodes'][node]['os_cores'])).replace(" ",""))
    cpuTable.add_row(row)

    # PMD reservation
    row = [str(sorted(topology['pmd_cores'])).replace(" ",""),"DPDK PMDs",
           bcolors.OKGREEN + topology['pmd_mask'] + bcolors.ENDC]
    for node in topology['nodes']:
        row.append(str(sorted(topology['nodes'][node]['pmd_cores'])).replace(" ",""))
    cpuTable.add_row(row)

    # Determine all remaining cores for each node
    row = ["N/A","Virtual Machines",None]
    for node in topology['nodes']:
        remaining_cores = topology['nodes'][node]['cpulist']
        row.append(str(sorted(remaining_cores)).replace(" ",""))
    cpuTable.add_row(row)

    # Print cpu table
    print "\nThe following table provides the breakdown of cores/threads per numa node"
    print "reserved for their respective function."
    print (cpuTable)

    # Provide cmdline parameters
    non_scheduled_cores = listToRanges(set(topology['host_cores']) - set(topology['os_cores']))
    print "\nRecommended kernel parameters:"
    print "\"GRUB_CMDLINE_LINUX=\"... isolcpus=%(s)s nohz_full=%(s)s rcu_nocbs=%(s)s" % \
          {'s': non_scheduled_cores}

    # Provide OSA overrides
    print "\nOverrides:"
    print "ovs_dpdk_lcore_mask: %s" % topology['host_mask']
    print "ovs_dpdk_pmd_cpu_mask: %s" % topology['pmd_mask']
    print "ovs_dpdk_pci_addresses: TBD"
    print "ovs_dpdk_socket_mem: %(s)s,%(s)s" % {'s': host_memory_per_node}

#    print json.dumps(topology)

if __name__ == "__main__":
    main()



#!/usr/bin/env python3

from pysnmp import debug as pysnmp_debug
from pysnmp.smi import builder, view, compiler
from pysnmp.hlapi import ObjectIdentity

import functools
import os

DEFAULT_MIB_SEARCH_PATHS = [
    "file://" + os.path.abspath('./mibs.snmplabs.com.zip'),  # local zip file
    "file://" + os.path.abspath('~/mibs.snmplabs.com.zip'),  # home dir zip file
    "file://" + os.path.abspath('./mibs.snmplabs.com/asn1'),  # local path
    "file://" + os.path.abspath('~/mibs.snmplabs.com/asn1'),  # home dir path
    'http://mibs.snmplabs.com/asn1/@mib@',  # hits the internet
]

DEFAULT_MIB_LOAD_MODULES = ['IF-MIB', 'SNMPv2-SMI', 'STARENT-MIB']

DEFAULT_CACHE_SIZE = 1024


class SnmpMibDecoder(object):
    __slots__ = ['mibBuilder', 'mibView']

    def __init__(self, additional_mib_search_paths=[], additional_mib_load_modules=[], debug=False, load_texts=True):
        if debug:  # Enable Debugging
            pysnmp_debug.setLogger(pysnmp_debug.Debug('all'))

        # The pysnmp libraries will compile MIB files into python files, and
        #   store them on the system in a cache directory under ~/.pysnmp/mibs
        #   It only needs to do this once as it encounters new MIBs, and not
        #   every time you run this program.  Order of the loading matters.
        mib_modules = additional_mib_load_modules + DEFAULT_MIB_LOAD_MODULES
        mib_sources = additional_mib_search_paths + DEFAULT_MIB_SEARCH_PATHS
        self.mibBuilder = builder.MibBuilder()
        self.mibBuilder.loadTexts = load_texts  # Loads mib text descriptions
        compiler.addMibCompiler(self.mibBuilder, sources=mib_sources)
        self.mibBuilder.loadModules(*mib_modules)
        self.mibView = view.MibViewController(self.mibBuilder)

    def cleanNumOid(self, num_oid):
        # strip first char from num_oid if starts with '.'
        if num_oid[0] == '.':
            return num_oid[1:]
        else:
            return num_oid

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getNameByNumOid(self, num_oid):
        str_oid = self.getStrOidByNumOid(num_oid)
        if str_oid is None:
            return None
        return str_oid.split('.')[-1]

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getDescByNumOid(self, num_oid):
        try:
            num_oid = self.cleanNumOid(num_oid)
            tuple_of_nums = tuple([int(i) for i in num_oid.split('.')])
            modName, symName, suffix = self._getNodeLocation(tuple_of_nums)
            mibNode, = self._importSymbols(modName, symName)
            desc = mibNode.getDescription()
            if len(desc) == 0:
                return None
            return desc
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getUnitsByNumOid(self, num_oid):
        try:
            num_oid = self.cleanNumOid(num_oid)
            tuple_of_nums = tuple([int(i) for i in num_oid.split('.')])
            modName, symName, suffix = self._getNodeLocation(tuple_of_nums)
            mibNode, = self._importSymbols(modName, symName)
            units = mibNode.getUnits()
            if len(units) == 0:
                return None
            return units
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getStrOidByNumOid(self, num_oid):
        try:
            num_oid = self.cleanNumOid(num_oid)
            num_segment_count = len(num_oid.split('.'))  # verification later

            x = ObjectIdentity(num_oid)
            x.resolveWithMib(self.mibView)
            str_oid = str.join('.', x.getLabel())

            str_segment_count = len(str_oid.split('.'))

            # Ensure the check allows for oids ending with '.0' denoting
            #   scaler value, which is non-named segment
            if (num_segment_count == str_segment_count) or (num_segment_count == str_segment_count + 1):
                return str_oid
            else:
                return None
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getTypeByNumOid(self, num_oid):
        try:
            num_oid = self.cleanNumOid(num_oid)
            tuple_of_nums = tuple([int(i) for i in num_oid.split('.')])
            modName, symName, suffix = self._getNodeLocation(tuple_of_nums)
            mibNode, = self._importSymbols(modName, symName)
            # Trims output "<class 'whatwewant'>"
            _type = str(type(mibNode.getSyntax()))[8:-2]
            return _type
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getTrapNumOidsByMib(self, mib_name):
        try:
            mib = self.mibView.mibBuilder.mibSymbols[mib_name]

            ret = []
            for oidName in mib.keys():
                mibNode = mib[oidName]
                if str(type(mibNode))[8:-2] != 'NotificationType':
                    continue
                num_oid = str.join('.', [str(i) for i in mibNode.getName()])
                ret.append(num_oid)
            return ret
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getVarNumOidsByTrap(self, num_oid):
        try:
            num_oid = self.cleanNumOid(num_oid)
            tuple_of_nums = tuple([int(i) for i in num_oid.split('.')])
            modName, symName, suffix = self._getNodeLocation(tuple_of_nums)
            mibNode, = self._importSymbols(modName, symName)

            ret = []
            for subNodeId in mibNode.getObjects():
                subNode = self.mibView.mibBuilder.mibSymbols[subNodeId[0]][subNodeId[1]]
                num_oid = str.join('.', [str(i) for i in subNode.getName()])
                ret.append(num_oid)
            return ret
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def getTrapNumOidBySymbols(self, mib_name, trap_name):
        try:
            mibNode, = self._importSymbols(mib_name, trap_name)
            num_oid = str.join('.', [str(i) for i in mibNode.getName()])
            return num_oid
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def castValueByNumOidType(self, num_oid, val_to_cast):
        try:
            num_oid = self.cleanNumOid(num_oid)
            tuple_of_nums = tuple([int(i) for i in num_oid.split('.')])
            modName, symName, suffix = self._getNodeLocation(tuple_of_nums)
            mibNode, = self._importSymbols(modName, symName)

            _type = type(mibNode.getSyntax())
            typed_val = _type(val_to_cast)
            return typed_val
        except Exception as e:
            # Not all OIDs can be decoded, esp if the MIBs have not been loaded
            print(e)
            return None

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def _getNodeLocation(self, *args, **kwargs):
        return self.mibView.getNodeLocation(*args, **kwargs)

    @functools.lru_cache(maxsize=DEFAULT_CACHE_SIZE)
    def _importSymbols(self, *args, **kwargs):
        return self.mibBuilder.importSymbols(*args, **kwargs)


def main():
    # TODO: Turn these into tests
    # name=starCardTemperature oid=1.3.6.1.4.1.8164.1.2.1.1.16
    #   type=pysnmp.proto.rfc1902.Gauge32
    smd = SnmpMibDecoder()
    num_oid = '.1.3.6.1.4.1.8164.1.2.1.1.16'
    str_oid = smd.getStrOidByNumOid(num_oid)
    _type = smd.getTypeByNumOid(num_oid)
    desc = smd.getDescByNumOid(num_oid)
    print(num_oid)
    print(str_oid)
    print(_type)
    print(desc)
    trap_oids = smd.getTrapNumOidsByMib('STARENT-MIB')
    # print(trap_oids)
    var_oids = smd.getVarNumOidsByTrap(trap_oids[1])
    print(var_oids)
    for var_oid in var_oids:
        str_oid = smd.getStrOidByNumOid(var_oid)
        _type = smd.getTypeByNumOid(var_oid)
        desc = smd.getDescByNumOid(var_oid)
        units = smd.getUnitsByNumOid(var_oid)
        print(var_oid)
        print(str_oid)
        print(_type)
        print(desc)
        print(units)
    num_oid = smd.getTrapNumOidBySymbols('STARENT-MIB', 'starCardTemperature')
    _type = smd.getTypeByNumOid(num_oid)
    typed_val = smd.castValueByNumOidType(num_oid, 99)
    print(num_oid)
    print(_type)
    print(typed_val)
    print(type(typed_val))

    # Test a scalar str conversion
    print("#####")
    num_oid = '.1.3.6.1.6.3.1.1.4.1.0'
    str_oid = smd.getStrOidByNumOid(num_oid)
    _type = smd.getTypeByNumOid(num_oid)
    desc = smd.getDescByNumOid(num_oid)
    print(num_oid)
    print(str_oid)
    print(_type)
    print(desc)


if __name__ == "__main__":
    main()

import subprocess
import xml.etree.ElementTree as ET

from lib.cuckoo.common.abstracts import LibVirtMachinery
from lib.cuckoo.common.exceptions import CuckooMachineError
from lib.cuckoo.common.misc import is_linux

try:
    import libvirt

    HAVE_LIBVIRT = True
except ImportError:
    HAVE_LIBVIRT = False


def is_tmpfs(ramdisk_dir):
    try:
        return subprocess.call(["df", "-t", "tmpfs", ramdisk_dir]) == 0
    except OSError:
        return False


class KVMRam(LibVirtMachinery):
    """KVM virtualization layer based on python-libvirt."""

    module_name = "kvmram"

    def _initialize_check(self):
        """Init KVM configuration to open libvirt dsn connection."""
        if not is_linux():
            raise CuckooMachineError("kvmram.conf only supports Linux platform!")
        self._sessions = {}
        if not self.options.kvmram.dsn:
            raise CuckooMachineError("KVM(i) DSN is missing, please add it to the config file")
        self.dsn = self.options.kvmram.dsn
        ramdisk_dir = self.options.kvmram.ramdisk_dir
        if not is_tmpfs(ramdisk_dir):
            raise CuckooMachineError('Make sure ramdisk dir "%s" is mounted as tmpfs type.' % ramdisk_dir)
        super(KVMRam, self)._initialize_check()

    def _get_interface(self, label):
        xml = ET.fromstring(self._lookup(label).XMLDesc())
        elem = xml.find("./devices/interface[@type='network']")
        if elem is None:
            return None
        elem = elem.find("target")
        if elem is None:
            return None

        return elem.attrib["dev"]

    def _disconnect(self, conn):
        """Disconnect, ignore request to disconnect."""
        pass

    def start(self, label, task):
        LOGGER.debug("Starting machine %s", label)

        if self._status(label) != self.POWEROFF:
            msg = "Trying to start a virtual machine that has not " "been turned off {0}".format(label)
            raise CuckooMachineError(msg)
        conn = self._connect()
        try:
            memfile = self.label_memfile_mapping[label]
            if 0 != conn.restore(memfile):
                raise CuckooMachineError(
                    "restore operation failed for domain {0} with " "memory dump file {1}!!".format(label, memfile)
                )
        except libvirt.libvirtError:
            raise CuckooMachineError("Unable to restore domain {0} from " "memory dump file {1}!!".format(label, memfile))
        finally:
            self._disconnect(conn)

    def initialize(self):
        """We initialize the kvm section.

        Args:
            module (str): base name of config. E.g. kvm for kvm.conf
        """
        super(KVMRam, self).initialize()
        self.label_memfile_mapping = {}
        machinery = self.options.get("kvmram")
        for machine in machinery["machines"]:
            kvs = self.options.get(machine)
            label = kvs.get("label")
            mem_fname = kvs.get("mem_dump_file")
            if label in self.label_memfile_mapping:
                raise CuckooMachineError("VM %s already added. Duplicate?" % (label))
            self.label_memfile_mapping[label] = mem_fname

    def store_vnc_port(self, label: str, task_id: int):
        xml = ET.fromstring(self._lookup(label).XMLDesc())
        port = int(xml.find("./devices/graphics").get("port", -1))
        if port and port != -1:
            self.db.set_vnc_port(task_id, port)
        else:
            print(f"Can't get iface for {label}")

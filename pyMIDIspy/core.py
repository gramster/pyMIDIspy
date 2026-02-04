"""
Core implementation of the SnoizeMIDISpy Python wrapper.

This module provides bindings to:
1. SnoizeMIDISpy framework - for capturing OUTGOING MIDI (sent to destinations)
2. CoreMIDI - for capturing INCOMING MIDI (received from sources)

Requires PyObjC for Objective-C block support (MIDIReadBlock callbacks).
"""

import ctypes
from ctypes import (
    POINTER,
    CFUNCTYPE,
    c_void_p,
    c_int32,
    c_uint32,
    c_uint16,
    c_uint64,
    c_uint8,
    c_char_p,
    byref,
    Structure,
    cast,
)
from dataclasses import dataclass
from typing import Callable, List, Optional, Set
import threading
import os

# PyObjC is required for Objective-C block support
import objc


# =============================================================================
# Error codes and exceptions
# =============================================================================

class MIDISpyError(Exception):
    """Base exception for MIDISpy errors."""
    pass


class DriverMissingError(MIDISpyError):
    """The MIDI spy driver is not installed."""
    pass


class DriverCommunicationError(MIDISpyError):
    """Failed to communicate with the MIDI spy driver."""
    pass


class ConnectionExistsError(MIDISpyError):
    """A connection to this destination already exists."""
    pass


class ConnectionNotFoundError(MIDISpyError):
    """No connection exists to this destination."""
    pass


# Error code constants from MIDISpyClient.h
_kMIDISpyDriverMissing = 1
_kMIDISpyDriverCouldNotCommunicate = 2
_kMIDISpyConnectionAlreadyExists = 3
_kMIDISpyConnectionDoesNotExist = 4

_ERROR_MAP = {
    _kMIDISpyDriverMissing: DriverMissingError,
    _kMIDISpyDriverCouldNotCommunicate: DriverCommunicationError,
    _kMIDISpyConnectionAlreadyExists: ConnectionExistsError,
    _kMIDISpyConnectionDoesNotExist: ConnectionNotFoundError,
}


def _check_status(status: int, operation: str = "operation"):
    """Check OSStatus and raise appropriate exception if non-zero."""
    if status == 0:
        return
    
    exc_class = _ERROR_MAP.get(status, MIDISpyError)
    raise exc_class(f"{operation} failed with status {status}")


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class MIDIMessage:
    """Represents a single MIDI message."""
    timestamp: int  # MIDITimeStamp (UInt64) in host time units
    data: bytes     # The raw MIDI bytes
    
    @property
    def status(self) -> Optional[int]:
        """Get the status byte if present."""
        return self.data[0] if self.data else None
    
    @property
    def channel(self) -> Optional[int]:
        """Get the MIDI channel (0-15) if this is a channel message."""
        if self.data and (self.data[0] & 0xF0) in range(0x80, 0xF0):
            return self.data[0] & 0x0F
        return None
    
    def __repr__(self):
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return f"MIDIMessage(timestamp={self.timestamp}, data=[{hex_data}])"


@dataclass
class MIDIDestination:
    """Represents a MIDI destination endpoint (output)."""
    endpoint_ref: int  # MIDIEndpointRef
    unique_id: int     # Unique identifier
    name: str          # Display name
    
    def __hash__(self):
        return hash(self.unique_id)
    
    def __eq__(self, other):
        if isinstance(other, MIDIDestination):
            return self.unique_id == other.unique_id
        return False


@dataclass
class MIDISource:
    """Represents a MIDI source endpoint (input)."""
    endpoint_ref: int  # MIDIEndpointRef
    unique_id: int     # Unique identifier
    name: str          # Display name
    
    def __hash__(self):
        return hash(self.unique_id)
    
    def __eq__(self, other):
        if isinstance(other, MIDISource):
            return self.unique_id == other.unique_id
        return False


# =============================================================================
# MIDI Packet structures for parsing
# =============================================================================

class MIDIPacket(Structure):
    """
    MIDIPacket structure:
        MIDITimeStamp timeStamp (UInt64)
        UInt16 length
        Byte data[256]  (variable length in practice)
    """
    _pack_ = 1  # Byte-aligned initially, but MIDIPacketNext handles actual alignment
    _fields_ = [
        ("timeStamp", c_uint64),
        ("length", c_uint16),
        # data follows, variable length
    ]


class MIDIPacketList(Structure):
    """
    MIDIPacketList structure:
        UInt32 numPackets
        MIDIPacket packet[1]  (variable length)
    """
    _fields_ = [
        ("numPackets", c_uint32),
        # packets follow
    ]


def _parse_midi_packet_list(data_ptr: c_void_p, data_length: int) -> List[MIDIMessage]:
    """
    Parse a MIDIPacketList from raw data.
    
    The data starts with:
        SInt32 endpointUniqueID
        MIDIPacketList packetList
    """
    messages = []
    
    if data_length < 4 + 4:  # sizeof(SInt32) + sizeof(numPackets)
        return messages
    
    # Read as bytes
    data = (c_uint8 * data_length).from_address(data_ptr)
    
    # Skip the endpointUniqueID (4 bytes)
    offset = 4
    
    # Read numPackets
    num_packets = int.from_bytes(bytes(data[offset:offset+4]), 'little')
    offset += 4
    
    for _ in range(num_packets):
        if offset + 10 > data_length:  # Need at least timestamp (8) + length (2)
            break
        
        # Read timestamp (8 bytes, little-endian)
        timestamp = int.from_bytes(bytes(data[offset:offset+8]), 'little')
        offset += 8
        
        # Read length (2 bytes, little-endian)
        length = int.from_bytes(bytes(data[offset:offset+2]), 'little')
        offset += 2
        
        if offset + length > data_length:
            break
        
        # Read MIDI data
        midi_data = bytes(data[offset:offset+length])
        offset += length
        
        # Handle alignment for next packet (4-byte alignment on ARM)
        # MIDIPacketNext accounts for this
        remainder = offset % 4
        if remainder != 0:
            offset += 4 - remainder
        
        messages.append(MIDIMessage(timestamp=timestamp, data=midi_data))
    
    return messages


# =============================================================================
# CoreMIDI types and loading
# =============================================================================

# Type aliases
MIDIClientRef = c_uint32
MIDIEndpointRef = c_uint32
MIDISpyClientRef = c_void_p
MIDISpyPortRef = c_void_p

# MIDIReadBlock callback type: void (^)(const MIDIPacketList *pktlist, void *srcConnRefCon)
# This is an Objective-C block. We'll handle it differently based on PyObjC availability.
MIDIReadBlockFunc = CFUNCTYPE(None, c_void_p, c_void_p)


def _create_midi_read_block(callback_func):
    """
    Create a MIDIReadBlock-compatible Objective-C block.
    
    MIDIReadBlock is an Objective-C block with signature:
        void (^)(const MIDIPacketList *pktlist, void *srcConnRefCon)
    
    We use PyObjC to create a proper block that CoreMIDI can retain/release.
    """
    # Block signature: void, pointer (packet list), pointer (refcon)
    # Using 'v' for void, '@?' for block, '^v' for void pointer
    block = objc.Block(callback_func, signature=b'v^v^v', argcount=2)
    return block


# =============================================================================
# Framework loading
# =============================================================================

def _find_framework():
    """Find the SnoizeMIDISpy framework."""
    # Get the package directory
    package_dir = os.path.dirname(__file__)
    
    # Possible locations for the framework
    possible_paths = [
        # Bundled in the package (primary location for installed package)
        os.path.join(package_dir, "lib", "SnoizeMIDISpy.framework", "SnoizeMIDISpy"),
        # Standard framework locations
        "/Library/Frameworks/SnoizeMIDISpy.framework/SnoizeMIDISpy",
        os.path.expanduser("~/Library/Frameworks/SnoizeMIDISpy.framework/SnoizeMIDISpy"),
        # Development: vendor build directory
        os.path.join(os.path.dirname(package_dir), "_build", "DerivedData", "Build", "Products", "Release", "SnoizeMIDISpy.framework", "SnoizeMIDISpy"),
        # Development: MIDIApps build directory
        os.path.join(os.path.dirname(package_dir), "vendor", "MIDIApps", "build", "Release", "SnoizeMIDISpy.framework", "SnoizeMIDISpy"),
    ]
    
    # Also check SNOIZE_MIDI_SPY_FRAMEWORK environment variable
    env_path = os.environ.get("SNOIZE_MIDI_SPY_FRAMEWORK")
    if env_path:
        possible_paths.insert(0, env_path)
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


def _load_coremidi():
    """Load CoreMIDI framework and set up function signatures."""
    coremidi = ctypes.CDLL("/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI")
    
    # Set up function signatures for common CoreMIDI functions
    # These must be set BEFORE calling the functions to avoid pointer truncation
    
    coremidi.MIDIGetNumberOfDestinations.argtypes = []
    coremidi.MIDIGetNumberOfDestinations.restype = c_uint32
    
    coremidi.MIDIGetDestination.argtypes = [c_uint32]
    coremidi.MIDIGetDestination.restype = c_uint32
    
    coremidi.MIDIGetNumberOfSources.argtypes = []
    coremidi.MIDIGetNumberOfSources.restype = c_uint32
    
    coremidi.MIDIGetSource.argtypes = [c_uint32]
    coremidi.MIDIGetSource.restype = c_uint32
    
    # Property access functions - CRITICAL: must use POINTER types correctly
    coremidi.MIDIObjectGetIntegerProperty.argtypes = [c_uint32, c_void_p, POINTER(c_int32)]
    coremidi.MIDIObjectGetIntegerProperty.restype = c_int32
    
    coremidi.MIDIObjectGetStringProperty.argtypes = [c_uint32, c_void_p, POINTER(c_void_p)]
    coremidi.MIDIObjectGetStringProperty.restype = c_int32
    
    # Client and port functions
    coremidi.MIDIClientCreate.argtypes = [c_void_p, c_void_p, c_void_p, POINTER(c_uint32)]
    coremidi.MIDIClientCreate.restype = c_int32
    
    coremidi.MIDIClientDispose.argtypes = [c_uint32]
    coremidi.MIDIClientDispose.restype = c_int32
    
    coremidi.MIDIInputPortCreateWithBlock.argtypes = [c_uint32, c_void_p, POINTER(c_uint32), c_void_p]
    coremidi.MIDIInputPortCreateWithBlock.restype = c_int32
    
    coremidi.MIDIPortDispose.argtypes = [c_uint32]
    coremidi.MIDIPortDispose.restype = c_int32
    
    coremidi.MIDIPortConnectSource.argtypes = [c_uint32, c_uint32, c_void_p]
    coremidi.MIDIPortConnectSource.restype = c_int32
    
    coremidi.MIDIPortDisconnectSource.argtypes = [c_uint32, c_uint32]
    coremidi.MIDIPortDisconnectSource.restype = c_int32
    
    return coremidi


def _load_corefoundation():
    """Load CoreFoundation framework and set up function signatures."""
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    
    # Set up proper function signatures to avoid pointer truncation on 64-bit systems
    # CFStringCreateWithCString returns a CFStringRef (pointer) - MUST be c_void_p, not default c_int!
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
    cf.CFStringCreateWithCString.restype = c_void_p
    
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_int32, c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    
    cf.CFRelease.argtypes = [c_void_p]
    cf.CFRelease.restype = None
    
    return cf


def _load_spy_framework(framework_path: Optional[str] = None):
    """Load the SnoizeMIDISpy framework."""
    if framework_path is None:
        framework_path = _find_framework()
    
    if framework_path is None:
        raise DriverMissingError(
            "Could not find SnoizeMIDISpy.framework. "
            "Please build the framework or set SNOIZE_MIDI_SPY_FRAMEWORK environment variable."
        )
    
    return ctypes.CDLL(framework_path)


# Global framework handles (lazy loaded)
_coremidi = None
_corefoundation = None
_spy_framework = None


def _get_coremidi():
    """Get the CoreMIDI framework handle."""
    global _coremidi
    if _coremidi is None:
        _coremidi = _load_coremidi()
    return _coremidi


def _get_corefoundation():
    """Get the CoreFoundation framework handle with proper function signatures."""
    global _corefoundation
    if _corefoundation is None:
        _corefoundation = _load_corefoundation()
    return _corefoundation


def _get_spy_framework():
    """Get the SnoizeMIDISpy framework handle."""
    global _spy_framework
    if _spy_framework is None:
        _spy_framework = _load_spy_framework()
    return _spy_framework


# =============================================================================
# CoreMIDI helper functions
# =============================================================================

def get_destinations() -> List[MIDIDestination]:
    """
    Get a list of all MIDI destinations in the system.
    
    Returns:
        List of MIDIDestination objects representing available MIDI outputs.
    """
    coremidi = _get_coremidi()
    cf = _get_corefoundation()
    
    destinations = []
    num_destinations = coremidi.MIDIGetNumberOfDestinations()
    
    for i in range(num_destinations):
        endpoint_ref = coremidi.MIDIGetDestination(i)
        if endpoint_ref == 0:
            continue
        
        # Get unique ID
        unique_id = c_int32()
        status = coremidi.MIDIObjectGetIntegerProperty(
            endpoint_ref,
            cf.CFStringCreateWithCString(None, b"uniqueID", 0),  # kMIDIPropertyUniqueID
            byref(unique_id)
        )
        
        # Get display name
        name = _get_endpoint_display_name(coremidi, cf, endpoint_ref)
        
        destinations.append(MIDIDestination(
            endpoint_ref=endpoint_ref,
            unique_id=unique_id.value,
            name=name
        ))
    
    return destinations


def _get_endpoint_display_name(coremidi, cf, endpoint_ref: MIDIEndpointRef) -> str:
    """Get the display name of a MIDI endpoint."""
    # Try to get the display name property
    cf_string_ptr = c_void_p()
    
    # Create the property name CFString
    prop_name = cf.CFStringCreateWithCString(None, b"displayName", 0)
    
    status = coremidi.MIDIObjectGetStringProperty(
        endpoint_ref,
        prop_name,
        byref(cf_string_ptr)
    )
    
    if status != 0 or cf_string_ptr.value is None:
        # Fall back to regular name
        prop_name = cf.CFStringCreateWithCString(None, b"name", 0)
        status = coremidi.MIDIObjectGetStringProperty(
            endpoint_ref,
            prop_name,
            byref(cf_string_ptr)
        )
    
    if status != 0 or cf_string_ptr.value is None:
        return f"Unknown Endpoint {endpoint_ref}"
    
    # Convert CFString to Python string
    buffer = ctypes.create_string_buffer(256)
    success = cf.CFStringGetCString(cf_string_ptr.value, buffer, 256, 0x08000100)  # kCFStringEncodingUTF8
    
    cf.CFRelease(cf_string_ptr)
    
    if success:
        return buffer.value.decode('utf-8')
    return f"Unknown Endpoint {endpoint_ref}"


def get_destination_by_name(name: str) -> Optional[MIDIDestination]:
    """
    Find a MIDI destination by its name.
    
    Args:
        name: The name of the destination (case-insensitive, partial match supported).
        
    Returns:
        MIDIDestination if found, None otherwise.
    """
    name_lower = name.lower()
    # First try exact match (case-insensitive)
    for dest in get_destinations():
        if dest.name.lower() == name_lower:
            return dest
    # Then try partial match
    for dest in get_destinations():
        if name_lower in dest.name.lower():
            return dest
    return None


def get_sources() -> List[MIDISource]:
    """
    Get a list of all MIDI sources in the system.
    
    Returns:
        List of MIDISource objects representing available MIDI inputs.
    """
    coremidi = _get_coremidi()
    cf = _get_corefoundation()
    
    sources = []
    num_sources = coremidi.MIDIGetNumberOfSources()
    
    for i in range(num_sources):
        endpoint_ref = coremidi.MIDIGetSource(i)
        if endpoint_ref == 0:
            continue
        
        # Get unique ID
        unique_id = c_int32()
        status = coremidi.MIDIObjectGetIntegerProperty(
            endpoint_ref,
            cf.CFStringCreateWithCString(None, b"uniqueID", 0),
            byref(unique_id)
        )
        
        # Get display name
        name = _get_endpoint_display_name(coremidi, cf, endpoint_ref)
        
        sources.append(MIDISource(
            endpoint_ref=endpoint_ref,
            unique_id=unique_id.value,
            name=name
        ))
    
    return sources


def get_source_by_name(name: str) -> Optional[MIDISource]:
    """
    Find a MIDI source by its name.
    
    Args:
        name: The name of the source (case-insensitive, partial match supported).
        
    Returns:
        MIDISource if found, None otherwise.
    """
    name_lower = name.lower()
    # First try exact match (case-insensitive)
    for src in get_sources():
        if src.name.lower() == name_lower:
            return src
    # Then try partial match
    for src in get_sources():
        if name_lower in src.name.lower():
            return src
    return None


# =============================================================================
# Driver installation
# =============================================================================

def install_driver_if_necessary() -> Optional[str]:
    """
    Install the MIDI spy driver if it's not already installed.
    
    This function must be called before creating a MIDIOutputClient. The driver
    enables capturing outgoing MIDI data.
    
    Returns:
        None on success, or an error message string on failure.
        
    Note:
        The driver is installed to ~/Library/Audio/MIDI Drivers/
        You may need to restart MIDI applications after installation.
    """
    spy = _get_spy_framework()
    
    # MIDISpyInstallDriverIfNecessary returns NSError* or NULL
    spy.MIDISpyInstallDriverIfNecessary.argtypes = []
    spy.MIDISpyInstallDriverIfNecessary.restype = c_void_p
    
    error_ptr = spy.MIDISpyInstallDriverIfNecessary()
    
    if error_ptr is None or error_ptr == 0:
        return None
    
    # Try to get error description
    # Load Foundation for NSError handling
    try:
        foundation = ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
        # In practice, we'd extract the localized description, but for simplicity:
        return "Driver installation failed (check that the framework bundle contains the driver)"
    except:
        return "Driver installation failed"


# =============================================================================
# MIDIOutputClient class (captures outgoing MIDI)
# =============================================================================

# Callback type for Python users
MIDICallback = Callable[[List[MIDIMessage], int], None]


class MIDIOutputClient:
    """
    A client for capturing outgoing MIDI messages sent to destinations.
    
    This class wraps the SnoizeMIDISpy framework to enable capturing MIDI
    data that is being sent to MIDI destinations by other applications.
    
    Example:
        def on_midi(messages, endpoint_id):
            for msg in messages:
                print(f"MIDI: {msg}")
        
        client = MIDIOutputClient(callback=on_midi)
        client.connect_destination(destination_unique_id)
        
        # ... keep running ...
        
        client.close()
    """
    
    def __init__(self, callback: MIDICallback, message_filter=None, framework_path: Optional[str] = None):
        """
        Create a new MIDI output client for capturing outgoing MIDI.
        
        Args:
            callback: Function called when MIDI messages are captured.
                      Signature: callback(messages: List[MIDIMessage], source_endpoint_unique_id: int)
            message_filter: Optional MessageFilter to filter messages before callback.
            framework_path: Optional path to the SnoizeMIDISpy framework.
        
        Raises:
            DriverMissingError: If the spy driver is not installed.
            DriverCommunicationError: If communication with the driver fails.
        """
        self._callback = callback
        self._message_filter = message_filter
        self._spy = _get_spy_framework()
        self._client_ref = c_void_p()
        self._port_ref = c_void_p()
        self._connected_endpoints: Set[int] = set()
        self._lock = threading.Lock()
        self._closed = False
        
        # Keep a reference to the callback to prevent garbage collection
        self._c_callback = self._create_c_callback()
        
        # Set up function signatures
        self._setup_function_signatures()
        
        # Create the client
        status = self._spy.MIDISpyClientCreate(byref(self._client_ref))
        _check_status(status, "MIDISpyClientCreate")
        
        # Create a port with our callback
        status = self._spy.MIDISpyPortCreate(
            self._client_ref,
            self._c_callback,
            byref(self._port_ref)
        )
        _check_status(status, "MIDISpyPortCreate")
    
    def _setup_function_signatures(self):
        """Set up ctypes function signatures for the spy framework."""
        self._spy.MIDISpyClientCreate.argtypes = [POINTER(c_void_p)]
        self._spy.MIDISpyClientCreate.restype = c_int32
        
        self._spy.MIDISpyClientDispose.argtypes = [c_void_p]
        self._spy.MIDISpyClientDispose.restype = c_int32
        
        self._spy.MIDISpyPortCreate.argtypes = [c_void_p, c_void_p, POINTER(c_void_p)]
        self._spy.MIDISpyPortCreate.restype = c_int32
        
        self._spy.MIDISpyPortDispose.argtypes = [c_void_p]
        self._spy.MIDISpyPortDispose.restype = c_int32
        
        self._spy.MIDISpyPortConnectDestination.argtypes = [c_void_p, MIDIEndpointRef, c_void_p]
        self._spy.MIDISpyPortConnectDestination.restype = c_int32
        
        self._spy.MIDISpyPortDisconnectDestination.argtypes = [c_void_p, MIDIEndpointRef]
        self._spy.MIDISpyPortDisconnectDestination.restype = c_int32
    
    def _create_c_callback(self):
        """Create the C callback function for receiving MIDI data."""
        # The MIDIReadBlock is an Objective-C block with signature:
        #   void (^)(const MIDIPacketList *pktlist, void *srcConnRefCon)
        
        def callback(packet_list_ptr, ref_con):
            if self._closed:
                return
            
            try:
                # Parse the packet list
                if packet_list_ptr is None:
                    return
                
                # Convert to integer address if needed
                if hasattr(packet_list_ptr, 'value'):
                    addr = packet_list_ptr.value
                elif isinstance(packet_list_ptr, int):
                    addr = packet_list_ptr
                else:
                    addr = int(packet_list_ptr)
                
                if addr == 0:
                    return
                
                # Parse packets from the MIDIPacketList
                messages = self._parse_packet_list(addr)
                
                # Get the source endpoint from refCon
                source_id = 0
                if ref_con:
                    if hasattr(ref_con, 'value'):
                        source_id = ref_con.value
                    elif isinstance(ref_con, int):
                        source_id = ref_con
                    else:
                        source_id = int(ref_con)
                
                # Call the user's callback
                if messages:
                    # Apply filter if set
                    if self._message_filter is not None:
                        messages = self._message_filter.filter_messages(messages)
                    if messages:
                        self._callback(messages, source_id)
                    
            except Exception as e:
                import sys
                print(f"Error in MIDI callback: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
        
        # Create the block/callback
        return _create_midi_read_block(callback)
    
    def _parse_packet_list(self, packet_list_addr: int) -> List[MIDIMessage]:
        """Parse a MIDIPacketList pointer into MIDIMessage objects."""
        messages = []
        
        if not packet_list_addr:
            return messages
        
        # Read the number of packets
        num_packets_ptr = ctypes.cast(packet_list_addr, POINTER(c_uint32))
        num_packets = num_packets_ptr[0]
        
        # Move to the first packet (after numPackets)
        offset = 4  # sizeof(UInt32)
        base_addr = packet_list_addr
        
        for _ in range(num_packets):
            # Read timestamp (8 bytes)
            timestamp_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint64))
            timestamp = timestamp_ptr[0]
            offset += 8
            
            # Read length (2 bytes)
            length_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint16))
            length = length_ptr[0]
            offset += 2
            
            # Read data
            data_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint8 * length))
            midi_data = bytes(data_ptr[0])
            offset += length
            
            # Align to 4 bytes for next packet
            remainder = offset % 4
            if remainder != 0:
                offset += 4 - remainder
            
            messages.append(MIDIMessage(timestamp=timestamp, data=midi_data))
        
        return messages
    
    def connect_destination(self, destination: MIDIDestination):
        """
        Start capturing MIDI messages sent to a destination.
        
        Args:
            destination: The MIDI destination to spy on.
            
        Raises:
            ConnectionExistsError: If already connected to this destination.
            MIDISpyError: If connection fails.
        """
        if self._closed:
            raise MIDISpyError("Client is closed")
        
        with self._lock:
            if destination.endpoint_ref in self._connected_endpoints:
                raise ConnectionExistsError(f"Already connected to {destination.name}")
            
            # Use the unique_id as the connection refcon so we can identify the source
            ref_con = c_void_p(destination.unique_id)
            
            status = self._spy.MIDISpyPortConnectDestination(
                self._port_ref,
                destination.endpoint_ref,
                ref_con
            )
            _check_status(status, f"Connect to {destination.name}")
            
            self._connected_endpoints.add(destination.endpoint_ref)
    
    def connect_destination_by_name(self, name: str):
        """
        Start capturing MIDI messages sent to a destination by its name.
        
        Args:
            name: The name of the destination (case-insensitive, partial match supported).
            
        Raises:
            ValueError: If no destination with this name exists.
            ConnectionExistsError: If already connected to this destination.
        """
        dest = get_destination_by_name(name)
        if dest is None:
            raise ValueError(f"No destination found matching '{name}'")
        self.connect_destination(dest)
    
    def disconnect_destination(self, destination: MIDIDestination):
        """
        Stop capturing MIDI messages from a destination.
        
        Args:
            destination: The MIDI destination to disconnect.
            
        Raises:
            ConnectionNotFoundError: If not connected to this destination.
        """
        if self._closed:
            return
        
        with self._lock:
            if destination.endpoint_ref not in self._connected_endpoints:
                raise ConnectionNotFoundError(f"Not connected to {destination.name}")
            
            status = self._spy.MIDISpyPortDisconnectDestination(
                self._port_ref,
                destination.endpoint_ref
            )
            _check_status(status, f"Disconnect from {destination.name}")
            
            self._connected_endpoints.discard(destination.endpoint_ref)
    
    def disconnect_destination_by_name(self, name: str):
        """
        Stop capturing MIDI messages from a destination by its name.
        
        Args:
            name: The name of the destination (case-insensitive, partial match supported).
        """
        dest = get_destination_by_name(name)
        if dest is None:
            raise ValueError(f"No destination found matching '{name}'")
        self.disconnect_destination(dest)
    
    def disconnect_all(self):
        """Disconnect from all destinations."""
        if self._closed:
            return
        
        # Get a snapshot of connected endpoints
        with self._lock:
            endpoints = list(self._connected_endpoints)
        
        for endpoint_ref in endpoints:
            try:
                self._spy.MIDISpyPortDisconnectDestination(self._port_ref, endpoint_ref)
            except:
                pass
        
        with self._lock:
            self._connected_endpoints.clear()
    
    @property
    def connected_destinations(self) -> List[MIDIDestination]:
        """Get list of currently connected destinations."""
        with self._lock:
            endpoint_refs = set(self._connected_endpoints)
        
        destinations = []
        for dest in get_destinations():
            if dest.endpoint_ref in endpoint_refs:
                destinations.append(dest)
        return destinations
    
    @property
    def message_filter(self):
        """Get the current message filter."""
        return self._message_filter
    
    @message_filter.setter
    def message_filter(self, value):
        """Set the message filter."""
        self._message_filter = value
    
    def close(self):
        """
        Close the MIDI spy client and release all resources.
        
        This method is idempotent and can be called multiple times.
        """
        if self._closed:
            return
        
        self._closed = True
        
        # Disconnect all destinations
        self.disconnect_all()
        
        # Dispose the port
        if self._port_ref:
            try:
                self._spy.MIDISpyPortDispose(self._port_ref)
            except:
                pass
            self._port_ref = c_void_p()
        
        # Dispose the client
        if self._client_ref:
            try:
                self._spy.MIDISpyClientDispose(self._client_ref)
            except:
                pass
            self._client_ref = c_void_p()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes the client."""
        self.close()
        return False
    
    def __del__(self):
        """Destructor - ensure resources are released."""
        self.close()


# =============================================================================
# MIDIInputClient class - for receiving incoming MIDI
# =============================================================================

class MIDIInputClient:
    """
    A client for receiving incoming MIDI messages from sources.
    
    This class uses standard CoreMIDI APIs to receive MIDI data from
    MIDI sources (inputs). This is the normal way to receive MIDI.
    
    Example:
        def on_midi(messages, source_id):
            for msg in messages:
                print(f"MIDI: {msg}")
        
        client = MIDIInputClient(callback=on_midi)
        client.connect_source(source)
        
        # ... keep running ...
        
        client.close()
    """
    
    def __init__(self, callback: MIDICallback, client_name: str = "PythonMIDI", message_filter=None):
        """
        Create a new MIDI input client.
        
        Args:
            callback: Function called when MIDI messages are received.
                      Signature: callback(messages: List[MIDIMessage], source_unique_id: int)
            client_name: Name for the MIDI client (visible in system).
            message_filter: Optional MessageFilter to filter messages before callback.
        """
        self._callback = callback
        self._message_filter = message_filter
        self._coremidi = _get_coremidi()
        self._cf = _get_corefoundation()
        
        self._client_ref = c_uint32()
        self._port_ref = c_uint32()
        self._connected_sources: Set[int] = set()
        self._source_refcons: dict = {}  # endpoint_ref -> unique_id
        self._lock = threading.Lock()
        self._closed = False
        
        # Keep reference to callback to prevent GC
        self._read_block = self._create_read_block()
        
        # Create MIDI client
        client_name_cf = self._cf.CFStringCreateWithCString(None, client_name.encode('utf-8'), 0)
        status = self._coremidi.MIDIClientCreate(client_name_cf, None, None, byref(self._client_ref))
        if status != 0:
            raise MIDISpyError(f"MIDIClientCreate failed with status {status}")
        
        # Create input port with our callback
        port_name_cf = self._cf.CFStringCreateWithCString(None, b"Input", 0)
        status = self._coremidi.MIDIInputPortCreateWithBlock(
            self._client_ref,
            port_name_cf,
            byref(self._port_ref),
            self._read_block
        )
        if status != 0:
            raise MIDISpyError(f"MIDIInputPortCreateWithBlock failed with status {status}")
    
    def _create_read_block(self):
        """Create the read block callback."""
        def callback(packet_list_ptr, ref_con):
            if self._closed:
                return
            
            try:
                if packet_list_ptr is None:
                    return
                
                # Convert to integer address
                if hasattr(packet_list_ptr, 'value'):
                    addr = packet_list_ptr.value
                elif isinstance(packet_list_ptr, int):
                    addr = packet_list_ptr
                else:
                    addr = int(packet_list_ptr)
                
                if addr == 0:
                    return
                
                # Parse packets
                messages = self._parse_packet_list(addr)
                
                # Get source ID from refcon
                source_id = 0
                if ref_con:
                    if hasattr(ref_con, 'value'):
                        source_id = ref_con.value if ref_con.value else 0
                    elif isinstance(ref_con, int):
                        source_id = ref_con
                    else:
                        try:
                            source_id = int(ref_con)
                        except:
                            source_id = 0
                
                if messages:
                    # Apply filter if set
                    if self._message_filter is not None:
                        messages = self._message_filter.filter_messages(messages)
                    if messages:
                        self._callback(messages, source_id)
                    
            except Exception as e:
                import sys
                print(f"Error in MIDI input callback: {e}", file=sys.stderr)
        
        return _create_midi_read_block(callback)
    
    def _parse_packet_list(self, packet_list_addr: int) -> List[MIDIMessage]:
        """Parse a MIDIPacketList pointer into MIDIMessage objects."""
        messages = []
        
        if not packet_list_addr:
            return messages
        
        # Read the number of packets
        num_packets_ptr = ctypes.cast(packet_list_addr, POINTER(c_uint32))
        num_packets = num_packets_ptr[0]
        
        # Move to the first packet (after numPackets)
        offset = 4  # sizeof(UInt32)
        base_addr = packet_list_addr
        
        for _ in range(num_packets):
            # Read timestamp (8 bytes)
            timestamp_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint64))
            timestamp = timestamp_ptr[0]
            offset += 8
            
            # Read length (2 bytes)
            length_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint16))
            length = length_ptr[0]
            offset += 2
            
            # Read data
            data_ptr = ctypes.cast(base_addr + offset, POINTER(c_uint8 * length))
            midi_data = bytes(data_ptr[0])
            offset += length
            
            # Align to 4 bytes for next packet
            remainder = offset % 4
            if remainder != 0:
                offset += 4 - remainder
            
            messages.append(MIDIMessage(timestamp=timestamp, data=midi_data))
        
        return messages
    
    def connect_source(self, source: MIDISource):
        """
        Start receiving MIDI messages from a source.
        
        Args:
            source: The MIDI source to connect to.
        """
        if self._closed:
            raise MIDISpyError("Client is closed")
        
        with self._lock:
            if source.endpoint_ref in self._connected_sources:
                raise ConnectionExistsError(f"Already connected to {source.name}")
            
            # Use unique_id as refcon
            ref_con = c_void_p(source.unique_id)
            self._source_refcons[source.endpoint_ref] = source.unique_id
            
            status = self._coremidi.MIDIPortConnectSource(
                self._port_ref,
                source.endpoint_ref,
                ref_con
            )
            if status != 0:
                raise MIDISpyError(f"MIDIPortConnectSource failed with status {status}")
            
            self._connected_sources.add(source.endpoint_ref)
    
    def connect_source_by_name(self, name: str):
        """Start receiving MIDI from a source by its name (case-insensitive, partial match supported)."""
        src = get_source_by_name(name)
        if src is None:
            raise ValueError(f"No source found matching '{name}'")
        self.connect_source(src)
    
    def disconnect_source(self, source: MIDISource):
        """Stop receiving MIDI messages from a source."""
        if self._closed:
            return
        
        with self._lock:
            if source.endpoint_ref not in self._connected_sources:
                raise ConnectionNotFoundError(f"Not connected to {source.name}")
            
            status = self._coremidi.MIDIPortDisconnectSource(
                self._port_ref,
                source.endpoint_ref
            )
            if status != 0:
                raise MIDISpyError(f"MIDIPortDisconnectSource failed with status {status}")
            
            self._connected_sources.discard(source.endpoint_ref)
            self._source_refcons.pop(source.endpoint_ref, None)
    
    def disconnect_source_by_name(self, name: str):
        """Stop receiving MIDI from a source by its name (case-insensitive, partial match supported)."""
        src = get_source_by_name(name)
        if src is None:
            raise ValueError(f"No source found matching '{name}'")
        self.disconnect_source(src)
    
    def disconnect_all(self):
        """Disconnect from all sources."""
        if self._closed:
            return
        
        with self._lock:
            endpoints = list(self._connected_sources)
        
        for endpoint_ref in endpoints:
            try:
                self._coremidi.MIDIPortDisconnectSource(self._port_ref, endpoint_ref)
            except:
                pass
        
        with self._lock:
            self._connected_sources.clear()
            self._source_refcons.clear()
    
    @property
    def connected_sources(self) -> List[MIDISource]:
        """Get list of currently connected sources."""
        with self._lock:
            endpoint_refs = set(self._connected_sources)
        
        sources = []
        for src in get_sources():
            if src.endpoint_ref in endpoint_refs:
                sources.append(src)
        return sources
    
    @property
    def message_filter(self):
        """Get the current message filter."""
        return self._message_filter
    
    @message_filter.setter
    def message_filter(self, value):
        """Set the message filter."""
        self._message_filter = value
    
    def close(self):
        """Close the MIDI input client and release resources."""
        if self._closed:
            return
        
        self._closed = True
        
        self.disconnect_all()
        
        if self._port_ref:
            try:
                self._coremidi.MIDIPortDispose(self._port_ref)
            except:
                pass
            self._port_ref = c_uint32()
        
        if self._client_ref:
            try:
                self._coremidi.MIDIClientDispose(self._client_ref)
            except:
                pass
            self._client_ref = c_uint32()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def __del__(self):
        self.close()

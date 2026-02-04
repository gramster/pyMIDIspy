# pyMIDIspy - Python MIDI Spy for macOS

A Python library for MIDI capture on macOS, providing both:
- **Outgoing MIDI capture** - Spy on MIDI being sent TO destinations (via SnoizeMIDISpy)
- **Incoming MIDI capture** - Receive MIDI FROM sources (via standard CoreMIDI)

## Overview

This library enables Python applications to:

1. **Capture outgoing MIDI** (`MIDIOutputClient`) - Capture what other applications are *sending* to MIDI outputs. This uses the SnoizeMIDISpy driver and is not possible with normal MIDI APIs.

2. **Receive incoming MIDI** (`MIDIInputClient`) - Standard MIDI input from sources like keyboards and controllers.

Use cases:
- Debugging MIDI communication between apps and hardware
- Recording/logging MIDI output from DAWs and other applications  
- Building MIDI monitoring and analysis tools
- Capturing both input and output for complete MIDI logging

## Requirements

- **macOS only** - Uses macOS-specific CoreMIDI
- **Python 3.8+**
- **Xcode** - Required to build the SnoizeMIDISpy framework from source
- **PyObjC** (installed automatically) - Required for Objective-C block callbacks

## Installation

### From Source (Recommended)

Clone the repository with submodules and build:

```bash
git clone --recursive https://github.com/gramster/pyMIDIspy.git
cd pyMIDIspy

# Build the framework and install the package
./build.sh

# Or install in development mode
pip install -e .
```

### From Wheel (if available)

```bash
pip install pyMIDIspy
```

Note: The wheel includes the pre-built SnoizeMIDISpy framework, so no Xcode is required.

### Manual Build

If you need more control over the build process:

```bash
# 1. Clone with submodules
git clone --recursive https://github.com/gramster/pyMIDIspy.git
cd pyMIDIspy

# 2. Initialize submodules if you didn't use --recursive
git submodule update --init --recursive

# 3. Build using pip (this compiles the framework automatically)
pip install .

# Or build a wheel
python -m build
```

## Quick Start

### Install the MIDI Spy Driver (First Time Only)

The spy driver needs to be installed once to enable outgoing MIDI capture:

```python
from pyMIDIspy import install_driver_if_necessary

# This installs the driver to ~/Library/Audio/MIDI Drivers/
error = install_driver_if_necessary()
if error:
    print(f"Driver installation failed: {error}")
else:
    print("Driver installed successfully!")
```

**Note:** You may need to restart any running MIDI applications after driver installation.

## Usage

### Incoming MIDI (from sources)

```python
from pyMIDIspy import MIDIInputClient, get_sources

def on_midi(messages, source_id):
    for msg in messages:
        print(f"Received: {msg.data.hex()}")

# List sources
for src in get_sources():
    print(f"  {src.name}")

# Receive MIDI from a source by name
with MIDIInputClient(callback=on_midi) as client:
    client.connect_source_by_name("KeyStep")  # case-insensitive, partial match
    
    import time
    while True:
        time.sleep(0.1)
```

### Outgoing MIDI (to destinations)

```python
from pyMIDIspy import MIDIOutputClient, get_destinations, install_driver_if_necessary

# Install the spy driver (first time only)
install_driver_if_necessary()

def on_midi(messages, dest_id):
    for msg in messages:
        print(f"Captured outgoing: {msg.data.hex()}")

# List destinations
for dest in get_destinations():
    print(f"  {dest.name}")

# Capture MIDI being sent to a destination by name
with MIDIOutputClient(callback=on_midi) as client:
    client.connect_destination_by_name("XR18")  # case-insensitive, partial match
    
    import time
    while True:
        time.sleep(0.1)
```

### Both directions

```python
from pyMIDIspy import MIDIOutputClient, MIDIInputClient, get_sources, get_destinations

def on_incoming(messages, source_id):
    for msg in messages:
        print(f"IN:  {msg.data.hex()}")

def on_outgoing(messages, dest_id):
    for msg in messages:
        print(f"OUT: {msg.data.hex()}")

# Create both clients
with MIDIInputClient(callback=on_incoming) as input_client, \
     MIDIOutputClient(callback=on_outgoing) as output_client:
    
    # Connect to all sources and destinations
    for src in get_sources():
        input_client.connect_source(src)
    for dest in get_destinations():
        output_client.connect_destination(dest)
    
    import time
    while True:
        time.sleep(0.1)
```

### Filtering Messages

Use `MessageFilter` to filter MIDI messages before they reach your callback:

```python
from pyMIDIspy import MIDIInputClient, MessageFilter

# Only receive note messages on channel 1
filter = MessageFilter(types=["note"], channels=[1])

client = MIDIInputClient(callback=on_midi, message_filter=filter)
```

**Common filtering patterns:**

```python
# Exclude timing clock and active sensing (common noise)
filter = MessageFilter(exclude_types=["timing_clock", "active_sensing"])

# Only note on/off messages
filter = MessageFilter(types=["note"])

# Only control change messages for specific controllers (mod wheel, volume, pan)
filter = MessageFilter(types=["control_change"], controllers=[1, 7, 10])

# Only messages on channels 1-4
filter = MessageFilter(channels=[1, 2, 3, 4])

# Combine: notes on channel 1, excluding note-off
filter = MessageFilter(types=["note_on"], channels=[1])
```

**Change filter at runtime:**

```python
client = MIDIInputClient(callback=on_midi)
client.connect_source(source)

# Later, add filtering
client.message_filter = MessageFilter(types=["note"])

# Remove filtering
client.message_filter = None
```

**Available message types for filtering:**

| Type | Description |
|------|-------------|
| `"note_off"` | Note Off messages |
| `"note_on"` | Note On messages (velocity > 0) |
| `"note"` | Both Note On and Note Off |
| `"control_change"` | Control Change (CC) messages |
| `"program_change"` | Program Change messages |
| `"pitch_bend"` | Pitch Bend messages |
| `"poly_pressure"` | Polyphonic Aftertouch |
| `"channel_pressure"` | Channel Aftertouch |
| `"sysex"` | System Exclusive messages |
| `"timing_clock"` | MIDI Clock (0xF8) |
| `"transport"` | Start, Stop, Continue |
| `"active_sensing"` | Active Sensing (0xFE) |
| `"realtime"` | All realtime (clock, transport, active sensing) |
| `"channel"` | All channel voice messages |
| `"system"` | All system messages |

### API Reference

#### Functions

##### `get_destinations() -> List[MIDIDestination]`
Get a list of all MIDI destinations (outputs) available on the system.

##### `get_destination_by_name(name: str) -> Optional[MIDIDestination]`
Find a MIDI destination by name (case-insensitive, partial match supported).

##### `get_sources() -> List[MIDISource]`
Get a list of all MIDI sources (inputs) available on the system.

##### `get_source_by_name(name: str) -> Optional[MIDISource]`
Find a MIDI source by name (case-insensitive, partial match supported).

##### `install_driver_if_necessary() -> Optional[str]`
Install the MIDI spy driver (for outgoing capture only). Returns `None` on success.

#### Classes

##### `MIDIInputClient`

Receives incoming MIDI from sources (standard CoreMIDI). No driver required.

```python
client = MIDIInputClient(callback=my_callback, client_name="MyApp", message_filter=filter)
```

**Methods:**
- `connect_source(source: MIDISource)` - Start receiving from a source
- `connect_source_by_name(name: str)` - Connect by name (case-insensitive, partial match)
- `disconnect_source(source: MIDISource)` - Stop receiving
- `disconnect_source_by_name(name: str)` - Disconnect by name
- `disconnect_all()` - Disconnect from all sources
- `close()` - Release all resources

**Properties:**
- `connected_sources` - List of currently connected sources
- `message_filter` - Get/set the MessageFilter (or None)

##### `MIDIOutputClient`

Captures outgoing MIDI sent to destinations. Requires the spy driver.

```python
client = MIDIOutputClient(callback=my_callback, message_filter=filter)
```

**Methods:**
- `connect_destination(destination: MIDIDestination)` - Start capturing from a destination
- `connect_destination_by_name(name: str)` - Connect by name (case-insensitive, partial match)
- `disconnect_destination(destination: MIDIDestination)` - Stop capturing
- `disconnect_destination_by_name(name: str)` - Disconnect by name
- `disconnect_all()` - Disconnect from all destinations
- `close()` - Release all resources

**Properties:**
- `connected_destinations` - List of currently connected destinations
- `message_filter` - Get/set the MessageFilter (or None)

##### `MessageFilter`

Filters MIDI messages by type, channel, or other criteria.

```python
filter = MessageFilter(
    types=["note", "control_change"],  # Include only these types
    exclude_types=["timing_clock"],    # Exclude these types
    channels=[1, 2],                   # Include only these channels (1-16)
    exclude_channels=[10],             # Exclude these channels
    controllers=[1, 7, 10],            # For CC: only these controller numbers
    notes=[60, 62, 64],                # For notes: only these note numbers
)
```

##### `MIDISource`

Represents a MIDI source endpoint (input).

##### `MIDIDestination`

Represents a MIDI destination endpoint (output).

##### `MIDIMessage`

Represents a captured MIDI message.

**Attributes:**
- `timestamp: int` - Host time when the message was sent
- `data: bytes` - Raw MIDI bytes

**Properties:**
- `status` - The status byte (or None)
- `channel` - The MIDI channel 0-15 (for channel messages)

#### Exceptions

- `MIDISpyError` - Base exception class
- `DriverMissingError` - The MIDI spy driver is not installed
- `DriverCommunicationError` - Failed to communicate with the driver
- `ConnectionExistsError` - Already connected to this destination
- `ConnectionNotFoundError` - Not connected to this destination

## How It Works

The SnoizeMIDISpy framework consists of two parts:

1. **MIDI Driver** (`MIDI Monitor.plugin`) - Installed in `~/Library/Audio/MIDI Drivers/`. This is a CoreMIDI driver that intercepts MIDI data sent to destinations.

2. **Client Framework** - Communicates with the driver via Mach messages to receive the captured MIDI data.

When you connect to a destination, the driver starts forwarding copies of all MIDI messages sent to that destination to your callback.

## Troubleshooting

### "Could not find SnoizeMIDISpy.framework"
Make sure you've built the framework and either:
- Set `SNOIZE_MIDI_SPY_FRAMEWORK` environment variable
- Copied the framework to `/Library/Frameworks/` or `~/Library/Frameworks/`

### "MIDI spy driver is missing"
Call `install_driver_if_necessary()` to install the driver. You may need to restart your DAW or MIDI applications after installation.

### No MIDI messages received
- Make sure the driver is installed (for outgoing capture)
- Verify the endpoint exists with `get_destinations()` or `get_sources()`
- Check that MIDI is actually being sent/received
- The MIDI Monitor app from MIDIApps can help debug

## Technical Notes

### Why PyObjC is required

CoreMIDI's `MIDIReadBlock` callback is an Objective-C block type:
```c
void (^)(const MIDIPacketList *pktlist, void *srcConnRefCon)
```

Blocks are not simple C function pointers—they're closures with a special memory layout that the runtime can retain/release. The SnoizeMIDISpy framework calls `CFRetain()` on the callback, which would crash with a plain C function pointer. PyObjC's `objc.Block` creates properly-structured blocks that are ABI-compatible with what CoreMIDI and the framework expect.

## Publishing to PyPI

To publish a new version to PyPI:

```bash
# 1. Build the wheel (this compiles the SnoizeMIDISpy framework)
./build.sh

# 2. Verify the package metadata and contents
twine check dist/*

# 3. (Recommended) Test on TestPyPI first
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ pyMIDIspy

# 4. Upload to PyPI
twine upload dist/*
```

**Notes:**
- The wheel is macOS-only and tagged as `macosx_10_13_universal2` (supports both arm64 and x86_64)
- Source distributions require Xcode to build the framework
- You'll need a PyPI account and API token (create at https://pypi.org/manage/account/token/)
- Store your token in `~/.pypirc` or use `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<your-token>`

## License

BSD License - see the LICENSE file.

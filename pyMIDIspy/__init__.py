"""
pyMIDIspy - Python MIDI capture for macOS

A Python library for capturing MIDI messages on macOS using the
SnoizeMIDISpy framework. This enables monitoring of MIDI data that is sent
to any MIDI destination, not just receiving incoming MIDI.

Usage:
    from pyMIDIspy import MIDIOutputClient, get_destinations

    # List available MIDI destinations
    for dest in get_destinations():
        print(dest.name)

    # Create an output client and monitor a destination by name
    def on_midi_message(messages, source_endpoint):
        for msg in messages:
            print(f"Captured: {msg}")

    client = MIDIOutputClient(callback=on_midi_message)
    client.connect_destination_by_name("XR18")  # partial match works too

    # Keep running...
    try:
        import time
        while True:
            time.sleep(0.1)
    finally:
        client.close()

Requirements:
    - macOS only
    - The SnoizeMIDISpy.framework must be installed and accessible
    - The MIDI spy driver must be installed (call install_driver_if_necessary())
"""

from .core import (
    # Clients
    MIDIOutputClient,
    MIDIInputClient,
    # Exceptions
    MIDISpyError,
    DriverMissingError,
    DriverCommunicationError,
    ConnectionExistsError,
    ConnectionNotFoundError,
    # Functions
    install_driver_if_necessary,
    get_destinations,
    get_destination_by_name,
    get_sources,
    get_source_by_name,
    # Data classes
    MIDIDestination,
    MIDISource,
    MIDIMessage,
    # Framework utilities
    _find_framework,
)

from .midi_utils import (
    parse_midi_message,
    ParsedMIDIMessage,
    MessageFilter,
    note_name,
    note_number,
    controller_name,
    # MIDI status constants
    NOTE_OFF,
    NOTE_ON,
    POLY_PRESSURE,
    CONTROL_CHANGE,
    PROGRAM_CHANGE,
    CHANNEL_PRESSURE,
    PITCH_BEND,
    SYSEX_START,
    TIMING_CLOCK,
    START,
    CONTINUE,
    STOP,
    # Message type constants for filtering
    MSG_NOTE_OFF,
    MSG_NOTE_ON,
    MSG_NOTE,
    MSG_POLY_PRESSURE,
    MSG_CONTROL_CHANGE,
    MSG_PROGRAM_CHANGE,
    MSG_CHANNEL_PRESSURE,
    MSG_PITCH_BEND,
    MSG_SYSEX,
    MSG_TIMING_CLOCK,
    MSG_TRANSPORT,
    MSG_ACTIVE_SENSING,
    MSG_REALTIME,
    MSG_CHANNEL,
    MSG_SYSTEM,
)

__all__ = [
    # Core classes
    "MIDIOutputClient",   # Capture outgoing MIDI (requires spy driver)
    "MIDIInputClient",    # Receive incoming MIDI (standard CoreMIDI)
    "MIDIDestination",
    "MIDISource",
    "MIDIMessage",
    # Filtering
    "MessageFilter",
    # Exceptions
    "MIDISpyError",
    "DriverMissingError",
    "DriverCommunicationError",
    "ConnectionExistsError",
    "ConnectionNotFoundError",
    # Functions
    "install_driver_if_necessary",
    "get_destinations",
    "get_destination_by_unique_id",
    "get_sources",
    "get_source_by_unique_id",
    "get_framework_path",
    # MIDI utilities
    "parse_midi_message",
    "ParsedMIDIMessage",
    "note_name",
    "note_number",
    "controller_name",
    # MIDI status byte constants
    "NOTE_OFF",
    "NOTE_ON",
    "POLY_PRESSURE",
    "CONTROL_CHANGE",
    "PROGRAM_CHANGE",
    "CHANNEL_PRESSURE",
    "PITCH_BEND",
    "SYSEX_START",
    "TIMING_CLOCK",
    "START",
    "CONTINUE",
    "STOP",
    # Message type constants for filtering
    "MSG_NOTE_OFF",
    "MSG_NOTE_ON",
    "MSG_NOTE",
    "MSG_POLY_PRESSURE",
    "MSG_CONTROL_CHANGE",
    "MSG_PROGRAM_CHANGE",
    "MSG_CHANNEL_PRESSURE",
    "MSG_PITCH_BEND",
    "MSG_SYSEX",
    "MSG_TIMING_CLOCK",
    "MSG_TRANSPORT",
    "MSG_ACTIVE_SENSING",
    "MSG_REALTIME",
    "MSG_CHANNEL",
    "MSG_SYSTEM",
]

__version__ = "1.1.0"


def get_framework_path():
    """
    Get the path to the bundled SnoizeMIDISpy framework.
    
    Returns:
        str: Path to the framework dylib, or None if not found.
    """
    return _find_framework()

"""
SnoizeMIDISpy Python wrapper

A Python library for capturing outgoing MIDI messages on macOS using the
SnoizeMIDISpy framework. This enables monitoring of MIDI data that is sent
to any MIDI destination, not just receiving incoming MIDI.

Usage:
    from snoize_midi_spy import MIDISpyClient, get_destinations

    # List available MIDI destinations
    for dest in get_destinations():
        print(f"{dest.name} (ID: {dest.unique_id})")

    # Create a spy client and monitor a destination
    def on_midi_message(messages, source_endpoint):
        for msg in messages:
            print(f"Captured: {msg}")

    client = MIDISpyClient(callback=on_midi_message)
    client.connect_destination(destination_unique_id)

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
    MIDISpyClient,
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
    get_destination_by_unique_id,
    get_sources,
    get_source_by_unique_id,
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
)

__all__ = [
    # Core classes
    "MIDISpyClient",      # Capture outgoing MIDI (requires spy driver)
    "MIDIInputClient",    # Receive incoming MIDI (standard CoreMIDI)
    "MIDIDestination",
    "MIDISource",
    "MIDIMessage",
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
    # Constants
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
]

__version__ = "1.0.0"


def get_framework_path():
    """
    Get the path to the bundled SnoizeMIDISpy framework.
    
    Returns:
        str: Path to the framework dylib, or None if not found.
    """
    return _find_framework()

#!/usr/bin/env python3
"""
Example script demonstrating the SnoizeMIDISpy Python wrapper.

This script monitors all MIDI destinations and prints captured MIDI messages.
"""

import sys
import time
from snoize_midi_spy import (
    MIDISpyClient,
    get_destinations,
    install_driver_if_necessary,
    MIDIMessage,
    DriverMissingError,
)


def format_midi_message(msg: MIDIMessage) -> str:
    """Format a MIDI message for display."""
    hex_data = " ".join(f"{b:02X}" for b in msg.data)
    
    # Decode common message types
    if not msg.data:
        return f"[empty]"
    
    status = msg.data[0]
    
    if status < 0x80:
        return f"[running status] {hex_data}"
    
    # Channel messages
    if status < 0xF0:
        channel = status & 0x0F
        msg_type = status & 0xF0
        
        type_names = {
            0x80: "Note Off",
            0x90: "Note On",
            0xA0: "Poly Pressure",
            0xB0: "Control Change",
            0xC0: "Program Change",
            0xD0: "Channel Pressure",
            0xE0: "Pitch Bend",
        }
        
        type_name = type_names.get(msg_type, "Unknown")
        return f"Ch {channel+1:2d} {type_name:16s} {hex_data}"
    
    # System messages
    system_names = {
        0xF0: "SysEx Start",
        0xF1: "MTC Quarter Frame",
        0xF2: "Song Position",
        0xF3: "Song Select",
        0xF6: "Tune Request",
        0xF7: "SysEx End",
        0xF8: "Timing Clock",
        0xFA: "Start",
        0xFB: "Continue",
        0xFC: "Stop",
        0xFE: "Active Sensing",
        0xFF: "System Reset",
    }
    
    type_name = system_names.get(status, "System")
    return f"       {type_name:16s} {hex_data}"


def main():
    print("SnoizeMIDISpy Python Example")
    print("=" * 50)
    print()
    
    # Install the driver if necessary
    print("Checking MIDI spy driver...")
    error = install_driver_if_necessary()
    if error:
        print(f"Warning: Could not install driver: {error}")
        print("The driver may already be installed, continuing...")
    else:
        print("Driver OK.")
    print()
    
    # List available destinations
    destinations = get_destinations()
    print(f"Found {len(destinations)} MIDI destination(s):")
    for i, dest in enumerate(destinations):
        print(f"  [{i}] {dest.name} (ID: {dest.unique_id})")
    print()
    
    if not destinations:
        print("No MIDI destinations available. Connect a MIDI device and try again.")
        return 1
    
    # Dictionary to map unique IDs to names
    dest_names = {dest.unique_id: dest.name for dest in destinations}
    
    # Callback for MIDI messages
    def on_midi(messages, source_id):
        source_name = dest_names.get(source_id, f"Unknown ({source_id})")
        for msg in messages:
            formatted = format_midi_message(msg)
            print(f"[{source_name:30s}] {formatted}")
    
    # Create the spy client
    try:
        print("Creating MIDI spy client...")
        with MIDISpyClient(callback=on_midi) as client:
            # Connect to all destinations
            for dest in destinations:
                try:
                    client.connect_destination(dest)
                    print(f"  Connected to: {dest.name}")
                except Exception as e:
                    print(f"  Could not connect to {dest.name}: {e}")
            
            print()
            print("Monitoring MIDI output. Press Ctrl+C to stop.")
            print("-" * 50)
            
            # Run until interrupted
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print()
                print("Stopped by user.")
                
    except DriverMissingError as e:
        print(f"Error: {e}")
        print()
        print("The MIDI spy driver is not installed. Please:")
        print("1. Build the SnoizeMIDISpy framework")
        print("2. Run this script again (it will attempt to install the driver)")
        print("3. Or use the MIDI Monitor app to install the driver")
        return 1
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

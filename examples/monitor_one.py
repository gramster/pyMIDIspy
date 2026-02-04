#!/usr/bin/env python3
"""
Example: Monitor a specific MIDI destination.

Usage:
    python monitor_one.py <unique_id>
    python monitor_one.py --list
"""

import sys
import time
from pyMIDIspy import (
    MIDIOutputClient,
    get_destinations,
    get_destination_by_unique_id,
    install_driver_if_necessary,
)


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        print("Available MIDI destinations:")
        for dest in get_destinations():
            print(f"  {dest.unique_id}: {dest.name}")
        print()
        print("Usage: python monitor_one.py <unique_id>")
        return 0
    
    # Parse the destination ID
    try:
        unique_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid unique ID")
        return 1
    
    # Find the destination
    dest = get_destination_by_unique_id(unique_id)
    if dest is None:
        print(f"Error: No destination found with ID {unique_id}")
        print("Use --list to see available destinations")
        return 1
    
    # Install driver
    install_driver_if_necessary()
    
    # Monitor
    def on_midi(messages, source_id):
        for msg in messages:
            hex_data = " ".join(f"{b:02X}" for b in msg.data)
            print(f"MIDI: {hex_data}")
    
    print(f"Monitoring: {dest.name}")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    with MIDIOutputClient(callback=on_midi) as client:
        client.connect_destination(dest)
        
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

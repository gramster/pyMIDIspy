#!/usr/bin/env python3
"""
Example: Monitor MIDI with parsed message output.

This example shows how to use the MIDI parsing utilities to display
human-readable MIDI messages.
"""

import sys
import time
from pyMIDIspy import (
    MIDIOutputClient,
    get_destinations,
    install_driver_if_necessary,
    parse_midi_message,
    controller_name,
)


def main():
    print("SnoizeMIDISpy - Parsed MIDI Monitor")
    print("=" * 50)
    
    # Install driver if needed
    install_driver_if_necessary()
    
    # Get destinations
    destinations = get_destinations()
    if not destinations:
        print("No MIDI destinations found.")
        return 1
    
    print(f"Found {len(destinations)} destinations:")
    for dest in destinations:
        print(f"  - {dest.name}")
    print()
    
    # Track destination names
    dest_names = {dest.unique_id: dest.name for dest in destinations}
    
    def on_midi(messages, source_id):
        source_name = dest_names.get(source_id, "Unknown")
        
        for msg in messages:
            parsed = parse_midi_message(msg.data)
            
            # Format output based on message type
            output_parts = [f"[{source_name[:20]:20s}]"]
            output_parts.append(f"{parsed.message_type:16s}")
            
            if parsed.channel:
                output_parts.append(f"Ch{parsed.channel:2d}")
            
            if parsed.note is not None:
                output_parts.append(f"{parsed.note_name:4s}")
                if parsed.velocity is not None:
                    output_parts.append(f"vel={parsed.velocity:3d}")
            
            if parsed.controller is not None:
                cc_name = controller_name(parsed.controller)
                output_parts.append(f"{cc_name}={parsed.value}")
            
            if parsed.program is not None:
                output_parts.append(f"program={parsed.program}")
            
            if parsed.pitch_bend is not None:
                output_parts.append(f"bend={parsed.pitch_bend:+5d}")
            
            if parsed.pressure is not None:
                output_parts.append(f"pressure={parsed.pressure}")
            
            # Also show raw hex for system messages
            if parsed.message_type in ("SysEx", "Unknown"):
                hex_data = " ".join(f"{b:02X}" for b in msg.data[:16])
                if len(msg.data) > 16:
                    hex_data += "..."
                output_parts.append(f"[{hex_data}]")
            
            print(" ".join(output_parts))
    
    print("Monitoring all MIDI output. Press Ctrl+C to stop.")
    print("-" * 50)
    
    with MIDIOutputClient(callback=on_midi) as client:
        for dest in destinations:
            try:
                client.connect_destination(dest)
            except Exception as e:
                print(f"Could not connect to {dest.name}: {e}")
        
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

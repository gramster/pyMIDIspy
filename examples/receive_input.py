#!/usr/bin/env python3
"""
Example: Receive incoming MIDI from sources.

This uses standard CoreMIDI to receive MIDI from inputs like keyboards.
No spy driver required.
"""

import sys
import time
from snoize_midi_spy import (
    MIDIInputClient,
    get_sources,
    parse_midi_message,
)


def main():
    print("MIDI Input Monitor")
    print("=" * 50)
    
    sources = get_sources()
    if not sources:
        print("No MIDI sources found. Connect a MIDI device and try again.")
        return 1
    
    print(f"Found {len(sources)} source(s):")
    for src in sources:
        print(f"  - {src.name}")
    print()
    
    source_names = {src.unique_id: src.name for src in sources}
    
    def on_midi(messages, source_id):
        source_name = source_names.get(source_id, f"Unknown ({source_id})")
        for msg in messages:
            parsed = parse_midi_message(msg.data)
            print(f"[{source_name[:25]:25s}] {parsed}")
    
    print("Receiving MIDI. Press Ctrl+C to stop.")
    print("-" * 50)
    
    with MIDIInputClient(callback=on_midi, client_name="PythonMIDIMonitor") as client:
        for src in sources:
            try:
                client.connect_source(src)
            except Exception as e:
                print(f"Could not connect to {src.name}: {e}")
        
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

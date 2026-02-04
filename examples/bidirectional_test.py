#!/usr/bin/env python3
"""Test bidirectional MIDI capture with MC-707.

This demonstrates:
1. MIDIInputClient - captures incoming MIDI from sources (working)
2. MIDIOutputClient - captures outgoing MIDI to destinations (requires driver restart)
"""

import sys
import warnings
sys.path.insert(0, "/Users/gram/repos/pyMIDIspy")
warnings.filterwarnings('ignore')

from pyMIDIspy import (
    MIDIInputClient, MIDIOutputClient,
    get_sources, get_destinations,
    get_source_by_name, get_destination_by_name,
    install_driver_if_necessary
)
import time

input_count = [0]
output_count = [0]

def on_midi_input(messages, source_id):
    """Callback for incoming MIDI."""
    for msg in messages:
        input_count[0] += 1
        status = msg.data[0] if msg.data else 0
        if status not in (0xF8, 0xFE):  # Skip clock and active sensing
            print(f"[INPUT] From source {source_id}: {msg}")

def on_midi_output(messages, endpoint_id):
    """Callback for captured outgoing MIDI."""
    for msg in messages:
        output_count[0] += 1
        status = msg.data[0] if msg.data else 0
        if status not in (0xF8, 0xFE):  # Skip clock and active sensing
            print(f"[OUTPUT] To endpoint {endpoint_id}: {msg}")

def main():
    print("=" * 60)
    print("pyMIDIspy Bidirectional MIDI Test")
    print("=" * 60)
    
    # List available endpoints
    sources = get_sources()
    destinations = get_destinations()
    
    print(f"\nMIDI Sources ({len(sources)}):")
    for src in sources:
        marker = " <-- MC-707" if "707" in src.name else ""
        print(f"  - {src.name}{marker}")
    
    print(f"\nMIDI Destinations ({len(destinations)}):")
    for dest in destinations:
        marker = " <-- MC-707" if "707" in dest.name else ""
        print(f"  - {dest.name}{marker}")
    
    # Find MC-707
    mc707_src = get_source_by_name("707")
    mc707_dest = get_destination_by_name("707")
    
    if not mc707_src:
        print("\n[ERROR] MC-707 source not found!")
        return
    
    # Test 1: MIDI Input
    print("\n" + "=" * 60)
    print("TEST 1: MIDI Input (receiving from MC-707)")
    print("=" * 60)
    
    try:
        input_client = MIDIInputClient(callback=on_midi_input)
        input_client.connect_source(mc707_src)
        print(f"[OK] Connected to source: {mc707_src.name}")
        
        print("\nListening for 5 seconds...")
        print("(MIDI clock messages are filtered)")
        time.sleep(5)
        
        input_client.close()
        print(f"\n[RESULT] Received {input_count[0]} messages (including clock)")
    except Exception as e:
        print(f"[ERROR] MIDI Input failed: {e}")
    
    # Test 2: MIDI Output Capture
    print("\n" + "=" * 60)
    print("TEST 2: MIDI Output Capture (monitoring sends to MC-707)")
    print("=" * 60)
    
    if not mc707_dest:
        print("[ERROR] MC-707 destination not found!")
    else:
        # Install driver if needed
        print("Installing spy driver if necessary...")
        error = install_driver_if_necessary()
        if error:
            print(f"[WARNING] Driver: {error}")
        else:
            print("[OK] Driver installed")
        
        try:
            output_client = MIDIOutputClient(callback=on_midi_output)
            output_client.connect_destination(mc707_dest)
            print(f"[OK] Connected to destination: {mc707_dest.name}")
            
            print("\nListening for 5 seconds...")
            print("(Send MIDI to MC-707 from another app)")
            time.sleep(5)
            
            output_client.close()
            print(f"\n[RESULT] Captured {output_count[0]} outgoing messages")
        except Exception as e:
            print(f"[ERROR] MIDI Output capture failed: {e}")
            print("        This usually means the spy driver needs a CoreMIDI restart.")
            print("        Try running: sudo killall -HUP coreaudiod")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    main()

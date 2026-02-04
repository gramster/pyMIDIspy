"""
MIDI message utilities and parsing helpers.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass

# MIDI Status Bytes
NOTE_OFF = 0x80
NOTE_ON = 0x90
POLY_PRESSURE = 0xA0
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
CHANNEL_PRESSURE = 0xD0
PITCH_BEND = 0xE0
SYSEX_START = 0xF0
MTC_QUARTER_FRAME = 0xF1
SONG_POSITION = 0xF2
SONG_SELECT = 0xF3
TUNE_REQUEST = 0xF6
SYSEX_END = 0xF7
TIMING_CLOCK = 0xF8
START = 0xFA
CONTINUE = 0xFB
STOP = 0xFC
ACTIVE_SENSING = 0xFE
SYSTEM_RESET = 0xFF

# Note names
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(note_number: int) -> str:
    """
    Convert a MIDI note number to a note name with octave.
    
    Args:
        note_number: MIDI note number (0-127)
        
    Returns:
        Note name like "C4", "F#2", etc.
    """
    octave = (note_number // 12) - 1
    name = NOTE_NAMES[note_number % 12]
    return f"{name}{octave}"


def note_number(name: str) -> int:
    """
    Convert a note name to a MIDI note number.
    
    Args:
        name: Note name like "C4", "F#2", "Bb3"
        
    Returns:
        MIDI note number (0-127)
    """
    name = name.strip().upper()
    
    # Handle flats by converting to sharps
    name = name.replace('BB', 'A#').replace('DB', 'C#').replace('EB', 'D#')
    name = name.replace('GB', 'F#').replace('AB', 'G#')
    
    # Parse note and octave
    if len(name) >= 2 and name[1] == '#':
        note_part = name[:2]
        octave = int(name[2:]) if len(name) > 2 else 4
    else:
        note_part = name[0]
        octave = int(name[1:]) if len(name) > 1 else 4
    
    note_index = NOTE_NAMES.index(note_part)
    return (octave + 1) * 12 + note_index


@dataclass
class ParsedMIDIMessage:
    """A decoded MIDI message with human-readable fields."""
    raw_data: bytes
    message_type: str
    channel: Optional[int] = None  # 1-16 for channel messages
    note: Optional[int] = None
    velocity: Optional[int] = None
    controller: Optional[int] = None
    value: Optional[int] = None
    program: Optional[int] = None
    pressure: Optional[int] = None
    pitch_bend: Optional[int] = None  # -8192 to 8191
    
    @property
    def note_name(self) -> Optional[str]:
        """Get the note name if this is a note message."""
        if self.note is not None:
            return note_name(self.note)
        return None
    
    def __str__(self) -> str:
        parts = [self.message_type]
        if self.channel is not None:
            parts.append(f"Ch{self.channel}")
        if self.note is not None:
            parts.append(f"Note={self.note_name}")
        if self.velocity is not None:
            parts.append(f"Vel={self.velocity}")
        if self.controller is not None:
            parts.append(f"CC{self.controller}={self.value}")
        if self.program is not None:
            parts.append(f"Prog={self.program}")
        if self.pressure is not None:
            parts.append(f"Press={self.pressure}")
        if self.pitch_bend is not None:
            parts.append(f"PB={self.pitch_bend}")
        return " ".join(parts)


def parse_midi_message(data: bytes) -> ParsedMIDIMessage:
    """
    Parse raw MIDI bytes into a structured message.
    
    Args:
        data: Raw MIDI bytes
        
    Returns:
        ParsedMIDIMessage with decoded fields
    """
    if not data:
        return ParsedMIDIMessage(raw_data=data, message_type="Empty")
    
    status = data[0]
    
    # Channel messages
    if status < 0xF0:
        channel = (status & 0x0F) + 1  # 1-16
        msg_type = status & 0xF0
        
        if msg_type == NOTE_OFF:
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Note Off",
                channel=channel,
                note=data[1] if len(data) > 1 else None,
                velocity=data[2] if len(data) > 2 else 0
            )
        elif msg_type == NOTE_ON:
            vel = data[2] if len(data) > 2 else 0
            # Note On with velocity 0 is equivalent to Note Off
            msg_name = "Note On" if vel > 0 else "Note Off"
            return ParsedMIDIMessage(
                raw_data=data,
                message_type=msg_name,
                channel=channel,
                note=data[1] if len(data) > 1 else None,
                velocity=vel
            )
        elif msg_type == POLY_PRESSURE:
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Poly Pressure",
                channel=channel,
                note=data[1] if len(data) > 1 else None,
                pressure=data[2] if len(data) > 2 else None
            )
        elif msg_type == CONTROL_CHANGE:
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Control Change",
                channel=channel,
                controller=data[1] if len(data) > 1 else None,
                value=data[2] if len(data) > 2 else None
            )
        elif msg_type == PROGRAM_CHANGE:
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Program Change",
                channel=channel,
                program=data[1] if len(data) > 1 else None
            )
        elif msg_type == CHANNEL_PRESSURE:
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Channel Pressure",
                channel=channel,
                pressure=data[1] if len(data) > 1 else None
            )
        elif msg_type == PITCH_BEND:
            if len(data) >= 3:
                # Pitch bend is 14-bit, LSB first
                lsb = data[1]
                msb = data[2]
                bend = ((msb << 7) | lsb) - 8192  # Center at 0
            else:
                bend = None
            return ParsedMIDIMessage(
                raw_data=data,
                message_type="Pitch Bend",
                channel=channel,
                pitch_bend=bend
            )
    
    # System messages
    system_names = {
        SYSEX_START: "SysEx",
        MTC_QUARTER_FRAME: "MTC Quarter Frame",
        SONG_POSITION: "Song Position",
        SONG_SELECT: "Song Select",
        TUNE_REQUEST: "Tune Request",
        SYSEX_END: "SysEx End",
        TIMING_CLOCK: "Timing Clock",
        START: "Start",
        CONTINUE: "Continue",
        STOP: "Stop",
        ACTIVE_SENSING: "Active Sensing",
        SYSTEM_RESET: "System Reset",
    }
    
    msg_type = system_names.get(status, f"Unknown (0x{status:02X})")
    return ParsedMIDIMessage(raw_data=data, message_type=msg_type)


# Controller number names (most common)
CONTROLLER_NAMES = {
    0: "Bank Select MSB",
    1: "Modulation Wheel",
    2: "Breath Controller",
    4: "Foot Controller",
    5: "Portamento Time",
    6: "Data Entry MSB",
    7: "Channel Volume",
    8: "Balance",
    10: "Pan",
    11: "Expression",
    32: "Bank Select LSB",
    64: "Sustain Pedal",
    65: "Portamento",
    66: "Sostenuto",
    67: "Soft Pedal",
    68: "Legato Footswitch",
    69: "Hold 2",
    120: "All Sound Off",
    121: "Reset All Controllers",
    122: "Local Control",
    123: "All Notes Off",
    124: "Omni Off",
    125: "Omni On",
    126: "Mono On",
    127: "Poly On",
}


def controller_name(cc_number: int) -> str:
    """Get the name of a MIDI controller number."""
    return CONTROLLER_NAMES.get(cc_number, f"CC {cc_number}")

import PIL.Image
import pathlib
import _ctypes
import struct
from ctypes import LittleEndianStructure, c_uint8, c_int16, c_int32, c_uint16, c_uint32, sizeof, cast, byref, addressof, POINTER, string_at

AU = struct.unpack('<H', b'AU')[0]

class CReprMixin:
    _hide_ = []
    def __repr__(self):
        cls = type(self)
        parts = [cls.__name__, "("]
        first = True
        for attr, _ in cls._fields_:
            if attr in cls._hide_: continue
            value = getattr(self, attr)
            if isinstance(value, _ctypes.Array):
                value = list(value)
            parts.extend((attr, '=', repr(value), ", "))
        parts[-1] = ')'
        return ''.join(parts)

# This header appears at the start of the file.
class SNXROMHeader(CReprMixin, LittleEndianStructure):
    _fields_ = [
        ('SNXROM', c_uint16 * 6),
        ('unknown1_ff', c_uint8 * 28),
        ('unknown2_0400', c_uint32),
        ('assetTableLength', c_uint32),
        ('unknown3_ff', c_uint8 * 464),
    ]

    _hide_ = frozenset(('unknown1_ff', 'unknown2_0400', 'unknown3_ff'))

# Usually there is a ROMMetaData as the first asset but Idle.bin lacks it
class ROMMetadata(CReprMixin, LittleEndianStructure):
    _fields_ = [
        ('type', c_uint16), # 0 for this block
        ('storyId', c_uint16),
        ('numberOfEyeAnimations', c_uint16),
        ('numberOfEyeBitmap', c_uint16),
        ('numberOfVideoSequences', c_uint16),
        ('numberOfAudioBlocks', c_uint16),
        ('fileSizeUpper', c_uint16),
        ('fileSizeLower', c_uint16),
        ('unknown_ff', c_uint8 * 16)
    ]

    _hide_ = frozenset(('unknown_ff',))

class EyeAnimationMetadata(CReprMixin, LittleEndianStructure):
    _hide_ = 'unknown'
    _fields_ = [
            ('animationId', c_uint16),
            ('startEyeId', c_uint16),
            ('numberOfEyeFrames', c_uint16),
            ('unknown', c_uint8 * 26)
    ]

class VideoAudioSequenceMetadata(CReprMixin, LittleEndianStructure):
    _hide_ = ['unknown', 'AU']
    _fields_ = [
            ('videoId', c_uint16),
            ('startAudioId', c_uint16),
            ('numberOfAudioblocks', c_uint16),
            ('unknown', c_uint8 * 26)
        ]

class AudioHeader(CReprMixin, LittleEndianStructure):
    #_hide_ = ['unknown']
    _fields_ = [
            ('AU', c_uint8 * 2),
            ('sampleRate', c_uint16),
            ('bitRate', c_uint16),
            ('channels', c_uint16),
            ('totalAudioFrames', c_uint32),
            ('sizeOfAudioBinary', c_uint32),
            ('markFlag', c_uint16),
            ('silenceFlag', c_uint16),
            ('mbf', c_uint16),
            ('pcs', c_uint16),
            ('rec', c_uint16),
            ('headerSize', c_uint16),
            ('audio32_type', c_uint16),
            ('stop_code', c_uint16),
            ('s_header', c_uint16),
    ]

    # In https://github.com/GMMan/aud32-decoder-client/blob/master/formats.py
    # followed by 0x140 bytes of "old samples"
    # followed by 2*self.sf btes of data

class EyeBitmap(LittleEndianStructure):
    _fields_ = [
            ('pixels', c_uint16 * 16384)
    ]

def cast_after(o, cls):
    r = byref(o, sizeof(o))
    return cast(byref(o, sizeof(o)), POINTER(cls))[0]

# Turns out this makes no sense
asset_by_type = {
        0: ROMMetadata,
        0x5441: AudioHeader,
        # otherwise it's a bitmap
}

def read_asset(asset_type, content, offset):
    cls = asset_by_type.get(asset_type.value)
    if cls is None:
        return None
    return cls.from_buffer(content, offset)

if __name__ == '__main__':
    with (pathlib.Path(__file__).parent / "assets/Intro.bin").open('rb') as f:
        content = bytearray(f.read())
    header = SNXROMHeader.from_buffer(content)
    print(header)
    assetTablePointers = cast_after(header, c_uint32 * header.assetTableLength);
    print(f"{header.assetTableLength} entries in asset table")

    audio_header = metadata = None
    audio_header_offset = None
    for o in assetTablePointers:
        asset_type = c_uint16.from_buffer(content, o)
        if asset_type.value == 0:
            print(f"Got metadata at offset {o}")
            metadata = ROMMetadata.from_buffer(content, o)
        if asset_type.value == AU:
            print(f"Got audio header at offset {o}")
            audio_header_offset = o
            audio_header = AudioHeader.from_buffer(content, o)

    eye_animations = []
    video_audio_sequences = []

    if metadata is not None:
        print(metadata)
        base = metadata
        for i in range(metadata.numberOfEyeAnimations):
            base = eye = cast_after(base, EyeAnimationMetadata)
            eye_animations.append(eye)
        for i in range(metadata.numberOfVideoSequences):
            base = seq = cast_after(base, VideoAudioSequenceMetadata)
            video_audio_sequences.append(seq)
        print(eye_animations)
        print(video_audio_sequences)

        seen = set()
        for e in eye_animations:
            print(e)
            for i in range(e.startEyeId, e.startEyeId + e.numberOfEyeFrames):
                if i in seen: continue
                seen.add(i)
                asset = (c_uint16 * (128*128)).from_buffer(content, assetTablePointers[i])
                PIL.Image.frombytes('RGB', (128,128), string_at(asset, 128*128*2), 'raw', 'RGB;16').save(f'eye{i}.png')

    if audio_header is not None:
        print()
        print(audio_header)
        audiodata = cast_after(audio_header, c_uint16 * (audio_header.sizeOfAudioBinary))
        markTableLength = cast_after(audiodata, c_uint16 * 1)
        print(audio_header.markTableSize)
        marks = cast_after(markTableLength, c_uint16 * markTableLength[0])
        #audiodata = (c_uint16 * (audio_header.sizeOfAudioBinary)).from_buffer(content, audio_header_offset + 2*audio_header.headerSize)
        print(audiodata)
        print(marks)

    import wave
    with wave.open('intro.wav', 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(string_at(audiodata, sizeof(audiodata)))

###     /**
###      * These identifiers start at 0xB to avoid collision 
###      * with other identifiers in the mark table.
###      */ 
###     uint16_t animationId;
###     uint16_t startEyeId;
###     uint16_t numberOfEyeFrames;
###     uint8_t _unknown[26]; // all 0xFF    
### } EyeAnimationMetadata;
### 
### /**
###  * An video audio sequence is defined by sequencing a number of audio blocks;
###  * specifying a start and a number of blocks.
###  * 
###  * (Most videos usually only have 1 associated audio block).
###  */ 

### typedef struct VideoAudioSequence : MetadataObject {
###     uint16_t videoId;
###     uint16_t startAudioId;
###     uint16_t numberOfAudioBlocks;
###     uint8_t _unknown[26]; // all 0xFF
### };
### 
### /**
###  * A bitmap which represents a single eye.
###  * Pixel encoding is RGB565.
###  * Pixel order starts from top-left.
###  * Each Bitmap is 128x128.
###  */
### struct EyeBitmap {
###     uint16_t pixels[16384];
### };
### 
### struct AudioHeader {
###     char8_t AU[2]; // always "AU"
###     uint16_t sampleRate; // always 16,000Hz
###     /**
###      * (compressed) bit rate = bitRate * 10
###      */ 
###     uint16_t bitRate; // always 3200 (32 kbps)
###     uint16_t channels; // always 1 (mono)    
###     uint32_t totalAudioFrames;
###     /**     
###      * size (in bytes) = sizeOfAudioBinary * 2
###      * 
###      * Also at 32 kbps, each block is 80 bytes, 
###      * so this is also equal to totalAudioFrames * 80
###      * 
###      * Note: Some 0xFFs will normally pad audio binary data afterwards.
###      */ 
###     uint32_t sizeOfAudioBinary;
###     uint16_t markFlag; // always 1 (enabled)
###     uint16_t silenceFlag; // always 0 (disabled)
###     uint16_t _unknown; // always 0x0
###     uint16_t __unknown; // always 0xFFFF
###     uint16_t ___unknown; // always 0x0
###     /**
###      * Audio binary data proceeds this header struct.
###      * Use the header size to figure its starting address.
###      */  
###     uint16_t headerSize;
###     MarkTable markTable;
### };
### 
### /**
###  * A table which coordinates eye animations and mouth movement, with audio.
###  */
### typedef struct MarkTable {
###     /**
###      * size (in bytes) = tableLength * 2
###      */  
###     uint16_t tableLength;
###     
###     /**
###      * Entries in the table are sequential.
###      * Each entry has a duration (milliseconds) and an identifier.
###      * The duration represents a period of time that elapses before the next action.
###      * 
###      * If the duration is equal or below 32,767 ms, then the entry is as follows:
###      * uint16_t duration;
###      * uint16_t identifier;
###      * 
###      * If the duration exceeds 32,767 ms, then the entry is 6 bytes is as follows:
###      * uint16_t durationUpper;
###      * uint16_t durationLower;
###      * uint16_t identifier;
###      * 
###      * Where:
###      * - durationUpper must have MSB set (i.e. durationUpper & 0x8000 === durationUpper is true)
###      * - duration = (durationUpper & 0x7FFF) << 16 + durationLower;
###      * 
###      * Identifiers:
###      * - 0x00 mouth closed
###      * - 0x01 mouth half open
###      * - 0x02 mouth fully open
###      * - >= 0x03 matches an animationId
###      * - >= 0x60 (To be confirmed)
###      */  
###     uint16_t tableWords[];
class MarkTable(CReprMixin, LittleEndianStructure):
    _fields_ = [
            ('tableLength', c_uint16),
            ('tableWords', c_uint16 * 1),
    ]

### 
### } MarkTable;



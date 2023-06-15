import PIL.Image
import json
import pathlib
import _ctypes
import struct
from ctypes import LittleEndianStructure, c_uint8, c_int16, c_int32, c_uint16, c_uint32, sizeof, cast, byref, addressof, POINTER, string_at
from dataclasses import dataclass

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

    def todict(self):
        return dict(
            (k, getattr(self, k))
            for k in ['animationId', 'startEyeId', 'numberOfEyeFrames'])

class VideoAudioSequenceMetadata(CReprMixin, LittleEndianStructure):
    _hide_ = ['unknown']
    _fields_ = [
            ('videoId', c_uint16),
            ('startAudioId', c_uint16),
            ('numberOfAudioBlocks', c_uint16),
            ('unknown', c_uint8 * 26)
        ]

    def todict(self):
        return dict(
            (k, getattr(self, k))
            for k in ['videoId', 'startAudioId', 'numberOfAudioBlocks'])

class AudioHeader(CReprMixin, LittleEndianStructure):
    _hide_ = ['AU']
    _fields_ = [
            ('AU', c_uint8 * 2),
            ('sampleRate', c_uint16),
            ('bitRate', c_uint16),
            ('channels', c_uint16),
            ('totalAudioFrames', c_uint32),
            ('sizeOfAudioBinary', c_uint32),
            ('markFlag', c_uint16),# always 1
            ('silenceFlag', c_uint16), # always 0
            ('mbf', c_uint16),
            ('pcs', c_uint16),
            ('rec', c_uint16),
            ('headerSize', c_uint16),
            ('audio32Type', c_uint16),
            #('stopCode', c_uint16),
            #('sHeader', c_uint16),
    ]

    def todict(self):
        return dict(
            (k, getattr(self, k))
            for k in ['sampleRate', 'bitRate', 'channels', 'totalAudioFrames', 'markFlag', 'silenceFlag', 'mbf', 'pcs', 'rec', 'headerSize', 'audio32Type']) #, 'stopCode', 'sHeader'])

    # In https://github.com/GMMan/aud32-decoder-client/blob/master/formats.py
    # followed by 0x140 bytes of "old samples"
    # followed by 2*self.sf btes of data

class EyeBitmap(LittleEndianStructure):
    _fields_ = [
            ('pixels', c_uint16 * 16384)
    ]

def castAt(o, cls):
    r = byref(o, 0)
    return cast(r, POINTER(cls))[0]

def castAfter(o, cls):
    r = byref(o, sizeof(o))
    return cast(r, POINTER(cls))[0]

def parseMarkTable(data):
    i = 0
    while i < len(data):
        if data[i] & 0x8000 == 0:
            duration = data[i]
            identifier = data[i+1]
            i += 2
        else:
            durationUpper = data[i] & 0x7fff
            durationLower = data[i+1]
            duration = (durationUpper << 16) | durationLower
            print(duration)
            if duration == 0x7fffffff:
                break
            identifier = data[i+2]
            i += 3
        yield duration, identifier

@dataclass
class SNXRom:
    metadata: ROMMetadata | None
    eyeAnimations: list[EyeAnimationMetadata]
    eyeImages: dict[int, PIL.Image]
    videoAudioSequences: list[VideoAudioSequenceMetadata]
    marks: list[int]
    audioHeaders: list[AudioHeader]
    audioData: list[bytes]

    def saveDirectory(self, path: pathlib.Path):
        path.mkdir(parents=True, exist_ok=True)
        story = {
                'storyId': self.metadata.storyId,
                'eyeAnimations': [animation.todict() for animation in self.eyeAnimations],
                'videoAudioSequences': [vas.todict() for vas in self.videoAudioSequences],
                'audioHeaders': [ah.todict() for ah in self.audioHeaders],
                'marks': self.marks
                }

        with (path / "story.json").open("w") as f:
            json.dump(story, f, indent=4)

        for i, img in self.eyeImages.items():
            img.save(path / f"eye{i:03d}.png")

        for i, data in enumerate(self.audioData):
            with (path / f"audio{i:03d}.bin").open("wb") as f:
                f.write(data)

    @classmethod
    def fromFile(cls, filename):
        with open(filename, "rb") as f:
            content = f.read()
        return cls.fromBuffer(content)

    @classmethod
    def fromBuffer(cls, data):
        content = bytearray(data)
        header = SNXROMHeader.from_buffer(content)
        assetTablePointers = castAfter(header, c_uint32 * header.assetTableLength);

        metadata: ROMMetadata | None = None
        audioHeaders: list[AudioHeader] = []
        audioData: list[bytes] = []
        marks: list[list[int]] = []

        for o in assetTablePointers:
            asset_type = c_uint16.from_buffer(content, o)
            if asset_type.value == 0:
                metadata = ROMMetadata.from_buffer(content, o)
            if asset_type.value == AU:
                audioHeader = AudioHeader.from_buffer(content, o)
                audioHeaders.append(audioHeader)
                print(audioHeader)
                markTableLength = castAfter(audioHeader, c_uint16 * 1)
                markTableData = castAfter(markTableLength, c_uint16 * (markTableLength[0]-1))
                marks.append(list(parseMarkTable(markTableData)))
                audiodata_c = castAfter(
                        castAt(audioHeader, c_uint16 * audioHeader.headerSize),
                        c_uint16 * (audioHeader.sizeOfAudioBinary))
                print(marks[-1])
                print(markTableLength[0])
                print(addressof(audioHeader))
                print(addressof(markTableData))
                print(addressof(castAfter(markTableData, c_uint16 * 1)))
                print(addressof(audiodata_c))
                audioData.append(bytes(audiodata_c))

        eyeAnimations: list[EyeAnimationMetadata] = []
        videoAudioSequences: list[VideoAudioSequenceMetadata] = []
        eyeImages: dict[int, PIL.Image] = {}

        if metadata is not None:
            base = metadata
            for i in range(metadata.numberOfEyeAnimations):
                base = eye = castAfter(base, EyeAnimationMetadata)
                eyeAnimations.append(eye)
            for i in range(metadata.numberOfVideoSequences):
                base = seq = castAfter(base, VideoAudioSequenceMetadata)
                videoAudioSequences.append(seq)

            for e in eyeAnimations:
                for i in range(e.startEyeId, e.startEyeId + e.numberOfEyeFrames):
                    if i in eyeImages: continue
                    asset = (c_uint16 * (128*128)).from_buffer(content, assetTablePointers[i])
                    eyeImages[i] = PIL.Image.frombytes('RGB', (128,128), string_at(asset, 128*128*2), 'raw', 'RGB;16')

        return cls(metadata=metadata, eyeAnimations=eyeAnimations, eyeImages=eyeImages, videoAudioSequences=videoAudioSequences, marks=marks, audioHeaders=audioHeaders, audioData=audioData)

if __name__ == '__main__':
    rom = SNXRom.fromFile('assets/Story01.bin')
    rom.saveDirectory(pathlib.Path('story01_out'))
    #rom.save_bin('intro_out.bin')

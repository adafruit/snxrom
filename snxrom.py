#!/usr/bin/python3
import PIL.Image
import array
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
        ('numberOfEyeImages', c_uint16),
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
    _hide_ = ['AU', 'padding']
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
            ('padding', c_uint16),
            #('sHeader', c_uint16),
    ]

    def todict(self):
        return dict(
            (k, getattr(self, k))
            for k in ['sampleRate', 'bitRate', 'channels', 'totalAudioFrames', 'markFlag', 'silenceFlag', 'mbf', 'pcs', 'rec', 'headerSize', 'audio32Type']) #, 'stopCode', 'sHeader'])

    # In https://github.com/GMMan/aud32-decoder-client/blob/master/formats.py
    # followed by 0x140 bytes of "old samples"
    # followed by 2*self.sf btes of data

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
            if duration == 0x7fffffff:
                break
            identifier = data[i+2]
            i += 3
        yield duration, identifier

def fakeheader(header: AudioHeader):
    """A header like the one that'll be written by the audio encode, without any marks"""
    h = AudioHeader.from_buffer_copy(header)
    h.markFlag = 0
    h.headerSize = 16
    return bytes(h)

def makeSNXROMHeader(n_asset):
    result = SNXROMHeader()
    for i, c in enumerate(b'SNXROM'):
        result.SNXROM[i] = c
    result.unknown1_ff[:] = b'\xff' * 28
    result.unknown2_0400 = 0x400
    result.assetTableLength = n_asset
    result.unknown3_ff[:] = b'\xff' * 464
    return result

def makeEyeData(eyeImage):
    return b'\x41\x55' * 128 * 128

def makeAudioAsset(header, data):
    return b'\0'

@dataclass
class SNXRom:
    storyId: int
    eyeAnimations: list[EyeAnimationMetadata]
    eyeImages: dict[int, PIL.Image]
    videoAudioSequences: list[VideoAudioSequenceMetadata]
    marks: list[int]
    audioHeaders: list[AudioHeader]
    audioData: list[bytes]

    @property
    def metadata(self):
        result = ROMMetadata()
        result.storyId = self.storyId
        result.numberOfEyeAnimations = len(self.eyeAnimations)
        result.numberOfEyeImages = len(self.eyeImages)
        result.numberOfVideoSequences = len(self.videoAudioSequences)
        result.numberOfAudioBlocks = len(self.audioHeaders)
        result.fileSizeUpper = 0 # to be filled
        result.fileSizeLower = 0 # to be filled
        result.unknown_ff[:] = b'\xff' * 16
        # TODO add eye & seq data
        return result

    @property
    def content(self):
        def pad():
            x = (-len(result) % 256)
            result.extend(b'\0' * x)
            assert len(result) % 256 == 0

        result = array.array('B')
        assets = []
        assets.append(self.metadata)
        for eyeImage in self.eyeImages:
            assets.append(makeEyeData(eyeImage))
        for header, data in zip(self.audioHeaders, self.audioData):
            assets.append(makeAudioAsset(header, data))
        n_assets = len(assets)

        result.extend(memoryview(makeSNXROMHeader(n_assets)).cast('B'))
        asset_offset_ptr = len(result)
        result.extend(b'\0\0\0\0' * n_assets)
        pad()
        metadata_offset = len(result)

        for asset in assets:
            print(f"asset size {len(memoryview(asset).cast('B'))}")

            result[asset_offset_ptr:asset_offset_ptr + 4] = array.array('B', struct.pack('<L', len(result)))
            asset_offset_ptr += 4
            result.extend(memoryview(asset).cast('B'))
            pad()

        metadata = SNXROMHeader.from_buffer(result, metadata_offset)
        metadata.fileSizeUpper = len(result) >> 16
        metadata.fileSizeLower = len(result) & 0xfff

        return result

    def saveBin(self, path: pathlib.Path):
        with path.open('wb') as f:
            f.write(self.content)

    def saveDirectory(self, path: pathlib.Path):
        path.mkdir(parents=True, exist_ok=True)
        story = {
                'storyId': self.storyId,
                'eyeAnimations': [animation.todict() for animation in self.eyeAnimations],
                'videoAudioSequences': [vas.todict() for vas in self.videoAudioSequences],
                'marks': self.marks
                }

        with (path / "story.json").open("w") as f:
            json.dump(story, f, indent=4)

        for i, img in self.eyeImages.items():
            img.save(path / f"eye{i:03d}.png")

        for i, (header, data) in enumerate(zip(self.audioHeaders, self.audioData)):
            with (path / f"audio{i:03d}.bin").open("wb") as f:
                f.write(fakeheader(header))
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
        print(header)
        assetTablePointers = castAfter(header, c_uint32 * header.assetTableLength);

        metadata: ROMMetadata | None = None
        audioHeaders: list[AudioHeader] = []
        audioData: list[bytes] = []
        marks: list[list[int]] = []

        for o, e in zip(assetTablePointers, assetTablePointers[1:] + [len(content)]):
            asset_type = c_uint16.from_buffer(content, o)
            print(f"asset {asset_type.value:#x} offset {o:#x} size {(e-o):#x}")
            if asset_type.value == 0:
                metadata = ROMMetadata.from_buffer(content, o)
            elif asset_type.value == AU:
                audioHeader = AudioHeader.from_buffer(content, o)
                audioHeaders.append(audioHeader)
                markTableLength = castAfter(audioHeader, c_uint16 * 1)
                markTableData = castAfter(markTableLength, c_uint16 * (markTableLength[0]-1))
                marks.append(list(parseMarkTable(markTableData)))
                audiodata_c = castAfter(
                        castAt(audioHeader, c_uint16 * audioHeader.headerSize),
                        c_uint16 * (audioHeader.sizeOfAudioBinary))
                audioData.append(bytes(audiodata_c))
            else:
                print(hex(o), hex(asset_type.value))

        eyeAnimations: list[EyeAnimationMetadata] = []
        videoAudioSequences: list[VideoAudioSequenceMetadata] = []
        eyeImages: dict[int, PIL.Image] = {}

        if metadata is not None:
            base = metadata
            for i in range(metadata.numberOfEyeAnimations):
                base = eye = castAfter(base, EyeAnimationMetadata)
                print(f"eye at {addressof(eye) - addressof(header):#x}")
                eyeAnimations.append(eye)
            for i in range(metadata.numberOfVideoSequences):
                base = seq = castAfter(base, VideoAudioSequenceMetadata)
                print(f"seq at {addressof(seq) - addressof(header):#x}")
                videoAudioSequences.append(seq)

            for e in eyeAnimations:
                for i in range(e.startEyeId, e.startEyeId + e.numberOfEyeFrames):
                    if i in eyeImages: continue
                    asset = (c_uint16 * (128*128)).from_buffer(content, assetTablePointers[i])
                    eyeImages[i] = PIL.Image.frombytes('RGB', (128,128), string_at(asset, 128*128*2), 'raw', 'RGB;16')

        return cls(storyId=0 if metadata is None else metadata.storyId, eyeAnimations=eyeAnimations, eyeImages=eyeImages, videoAudioSequences=videoAudioSequences, marks=marks, audioHeaders=audioHeaders, audioData=audioData)

if __name__ == '__main__':
    rom = SNXRom.fromFile('assets/Story01.bin')
    rom.saveDirectory(pathlib.Path('story01_out'))
    rom.saveBin(pathlib.Path('intro_out.bin'))

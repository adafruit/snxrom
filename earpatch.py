#!/usr/bin/python3
import ctypes
import json
import random
import struct
import wave
import snxrom
import click

def sizeof(obj):
    return len(memoryview(obj).cast('B'))

def getFirstAU(content, assetTablePointers):
    for i, (o, e) in enumerate(zip(assetTablePointers, assetTablePointers[1:] + [len(content)])):
        asset_type = struct.unpack('<H', content[o:o+2])[0]
        if asset_type == snxrom.AU:
            return i, memoryview(content[o:e])
    raise ValueError("No AU chunk found in file")

# On my bear, code 2 goes past "mouth open" and starts to close again,
# so I'm calling that "middle".
CLOSED, OPEN, MIDDLE = range(3)

# To go from state X to state Y, start LATENCY[X][Y]ms earlier than what the
# rhubarb data says
LATENCY = {
    CLOSED: {
        CLOSED: 0, OPEN: 200, MIDDLE: 200,
    },
    OPEN: {
        CLOSED: 200, OPEN: 0, MIDDLE: 0,
    },
    MIDDLE: {
        CLOSED: 200, OPEN: 150, MIDDLE: 0,
    }
}

rhubarb_mouth_map = {
        'A': CLOSED,
        'F': CLOSED,
        'X': CLOSED,

        'B': MIDDLE,
        'C': MIDDLE,
        'G': MIDDLE,
        'H': MIDDLE,

        'D': OPEN,
        'E': OPEN,
        }

def rhubarb_to_timestamp(rhubarb_json):
    last = 0
    result = [(0, CLOSED)]
    old_value = CLOSED
    for row in rhubarb_json['mouthCues']:
        start = round(row['start'] * 1000)
        value = rhubarb_mouth_map[row['value']]
        if value != old_value:
            start = max(last, start - LATENCY[old_value][value])
            result.append((start, value))
        old_value = value
    return result

def random_eye_timestamp(duration_ms, random_eyes_median, random_eyes_std_dev):
    now = 0
    result = [(0, 11)] # Start with an animation
    while now < duration_ms:
        delta = random.gauss(random_eyes_median, random_eyes_std_dev) * 1000
        now += int(max(0, delta))
        result.append((now, random.randint(11, 14))) # Assume these are the valid animation numbers (true for Intro.bin)
    return result

def timestamp_to_delay(seq):
    last = 0
    result = []
    for now, action in seq:
        result.append((now-last, action))
        last = now
    return result

@click.command
@click.option("--au", type=click.File('rb'), default=None, help="Previously converted sound file with 'AU' magic header")
@click.option("--wav", type=wave.open, default=None, help="Wave file, 16-bit mono at 16kHz")
@click.option("--rhubarb-json", type=click.File('r'), default=None, help="Rhubarb json file for mouth positions")
@click.option("--no-mouth", default=False, is_flag=True, help="Just keep your mouth shut")
@click.option("--random-eyes/--no-random-eyes", default=True, is_flag=True, help="Use random eye animations (default: None)")
@click.option("--random-eyes-median", default=30., help="The median time between eye animations")
@click.option("--random-eyes-std-dev", default=6., help="The standard deviation of the animation time")
@click.argument("input-file", type=click.File('rb'))
@click.argument("output-file", type=click.File('wb'))
def earpatch(au, wav, rhubarb_json, no_mouth, random_eyes, random_eyes_median, random_eyes_std_dev, input_file, output_file):
    content = bytearray(input_file.read())
    file_header, assetTablePointers = snxrom.parseHeaderAndPointers(content)

    AUIdx, au_chunk = getFirstAU(content, assetTablePointers)
    AUoffset = assetTablePointers[AUIdx]
    file_header.assetTableLength = 1 + AUIdx # Remove any following items from asset table (assumed to be audio chunks)

    if au is not None:
        au_chunk = bytearray(au.read())
        au_header = snxrom.AudioHeader.from_buffer(au_chunk)
        au_payload = au_chunk[au_header.headerSize*2:(au_header.headerSize+au_header.sizeOfAudioBinary)*2]
        print(au_header, au_header.padding)
        duration_ms = round(au_header.sizeOfAudioBinary * 16 * 100 / au_header.bitRate)
    elif wav is not None:
        import g722_1_mod as m
        wav_params = wav.getparams()
        assert wav_params.framerate in (16000, 32000)
        assert wav_params.sampwidth == 2
        assert wav_params.nchannels == 1

        samples = wav.readframes(wav.getnframes())
        if wav_params.framerate >= 24000:
            bitRate = 3200
            inchunksize = 640
            outchunksize = 80
        else:
            bitRate = 1600
            inchunksize = 320
            outchunksize = 40
        au_payload = m.encode(samples, inchunksize, outchunksize)
        duration_ms = wav.getnframes() / 16

        au_header = snxrom.AudioHeader(snxrom.AU, sampleRate=wav_params.framerate, bitRate=bitRate, channels=1, totalAudioFrames=len(au_payload) // outchunksize, sizeOfAudioBinary = len(au_payload) // 2, markFlag=True, silenceFlag=False, headerSize=16, audio32Type=0xffff, padding=0xffff)

    if rhubarb_json is not None:
        rhubarb_timings = json.load(rhubarb_json)
        mouth_timings = rhubarb_to_timestamp(rhubarb_timings)
        if random_eyes:
            eye_timings = random_eye_timestamp(duration_ms, random_eyes_median, random_eyes_std_dev)
        else:
            eye_timings = []
        mark_timings = timestamp_to_delay(sorted(mouth_timings + eye_timings))
        mark_data = snxrom.encodeMarkTable(mark_timings)
    elif no_mouth:
        mark_data = b''
    else:
        mark_data = au_chunk[32:au_header.headerSize*2]

    au_header.markFlag = bool(mark_data)
    au_header.headerSize = (sizeof(au_header) + sizeof(mark_data)) // 2 # in units of uint16

    newChunk = bytearray()
    newChunk.extend(memoryview(au_header).cast('B'))
    newChunk.extend(memoryview(mark_data).cast('B'))
    newChunk.extend(memoryview(au_payload).cast('B'))
    print(f"Old chunk length {len(au_chunk)}")
    print(f"New chunk length {len(newChunk)}")
    with open("new.au", "wb") as f: f.write(newChunk)

    content = bytearray(content[:AUoffset])
    content.extend(memoryview(au_header).cast('B'))
    content.extend(memoryview(mark_data).cast('B'))
    content.extend(memoryview(au_payload).cast('B'))

    if len(content) % 512 != 0:
        content.extend(b'\xff' * (512 - len(content) % 512))
    output_file.write(content)

if __name__ == '__main__':
    earpatch()

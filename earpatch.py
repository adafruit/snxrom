#!/usr/bin/python3
import json
import random
import ctypes
import struct
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

def arbitrary_mouth_data(duration_s, n_states=10):
    print(f"{duration_s=}")
    duration_ms = round(duration_s * 1000)
    result = []
    states = [0, 1, 0, 2]
    for i in range(n_states):
        result.append([duration_ms // n_states, states[i % 4]])
    return result

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

def random_eye_timestamp(duration_ms):
    now = 0
    result = [(0, 11)]
    while now < duration_ms:
        now += random.randint(250, 1000)
        result.append((now, random.randint(11, 14)))
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
@click.option("--rhubarb-json", type=click.File('r'), default=None, help="Rhubarb json file for mouth positions")
@click.option("--no-mouth", default=False, is_flag=True, help="Just keep your mouth shut")
@click.option("--random-eyes", default=False, is_flag=True, help="Use random eye animations (default: None)")
@click.argument("input-file", type=click.File('rb'))
@click.argument("output-file", type=click.File('wb'))
def earpatch(au, rhubarb_json, no_mouth, random_eyes, input_file, output_file):
    content = bytearray(input_file.read())
    file_header, assetTablePointers = snxrom.parseHeaderAndPointers(content)

    AUIdx, au_chunk = getFirstAU(content, assetTablePointers)
    AUoffset = assetTablePointers[AUIdx]
    file_header.assetTableLength = 1 + AUIdx # Remove any following items from asset table (assumed to be audio chunks)

    if au is not None:
        au_chunk = bytearray(au.read())

    au_header = snxrom.AudioHeader.from_buffer(au_chunk)
    duration_ms = round(au_header.sizeOfAudioBinary * 16 * 100 / au_header.bitRate)

    au_payload = au_chunk[au_header.headerSize*2:(au_header.headerSize+au_header.sizeOfAudioBinary)*2]
    with open("payload.au", "wb") as f: f.write(au_chunk)

    print(f"{len(au_payload)=}")

    print(f"{sizeof(au_header)=}")
    if rhubarb_json is not None:
        rhubarb_timings = json.load(rhubarb_json)
        mouth_timings = rhubarb_to_timestamp(rhubarb_timings)
        if random_eyes:
            eye_timings = random_eye_timestamp(duration_ms)
        else:
            eye_timings = []
        print(mouth_timings)
        print(eye_timings)
        mark_timings = timestamp_to_delay(sorted(mouth_timings + eye_timings))
        print(mark_timings)
        mark_data = snxrom.encodeMarkTable(mark_timings)
    elif no_mouth:
        mark_data = b''
    else:
        mark_data = au_chunk[32:au_header.headerSize*2]

    au_header.markFlag = bool(mark_data)
    au_header.headerSize = (sizeof(au_header) + sizeof(mark_data)) // 2 # in units of uint16

    print(f"{mark_data=}")
    print(f"{au_header=}")

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

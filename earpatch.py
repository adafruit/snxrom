#!/usr/bin/python3
import json
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

OPEN, MIDDLE, CLOSED = range(3)

rhubarb_mouth_map = {
        'A': CLOSED,
        'B': MIDDLE,
        'C': MIDDLE,
        'D': OPEN,
        'E': OPEN,
        'F': CLOSED,
        }

def rhubarb_to_ruxpin(rhubarb_json):
    last = 0
    result = []
    for row in rhubarb_json['mouthCues']:
        end = round(row['end'] * 1000) # stamps are said to be in "ms"
        start = round(row['start'] * 1000)
        if start != last:  # mouth closed during time without viseme
            duration = start - last
            result.append((duration, 0))
            last = start

        value = rhubarb_mouth_map[row['value']]
        duration = end - last
        last = end
        result.append((duration, value))
    i = 0
    print(result)
    while i+1 < len(result):
        if result[i][1] == result[i+1][1]:
            result[i] = (result[i][0] + result[i+1][0], result[i][1])
            del result[i+1]
        else:
            i += 1
    print(result)
    return result

@click.command
@click.option("--au", type=click.File('rb'), default=None, help="Previously converted sound file with 'AU' magic header")
@click.option("--rhubarb-json", type=click.File('r'), default=None, help="Rhubarb json file for mouth positions")
@click.option("--no-mouth", default=False, is_flag=True, help="Just keep your mouth shut")
@click.argument("input-file", type=click.File('rb'))
@click.argument("output-file", type=click.File('wb'))
def earpatch(au, rhubarb_json, no_mouth, input_file, output_file):
    content = bytearray(input_file.read())
    file_header, assetTablePointers = snxrom.parseHeaderAndPointers(content)

    AUIdx, au_chunk = getFirstAU(content, assetTablePointers)
    AUoffset = assetTablePointers[AUIdx]
    file_header.assetTableLength = 1 + AUIdx # Remove any following items from asset table (assumed to be audio chunks)

    if au is not None:
        au_chunk = bytearray(au.read())

    au_header = snxrom.AudioHeader.from_buffer(au_chunk)

    au_payload = au_chunk[au_header.headerSize*2:(au_header.headerSize+au_header.sizeOfAudioBinary)*2]
    with open("payload.au", "wb") as f: f.write(au_chunk)

    print(f"{len(au_payload)=}")

    print(f"{sizeof(au_header)=}")
    if rhubarb_json is not None:
        rhubarb_timings = json.load(rhubarb_json)
        mouth_timings = rhubarb_to_ruxpin(rhubarb_timings)
        mouth_data = snxrom.encodeMarkTable(mouth_timings)
    elif no_mouth:
        mouth_data = b''
    else:
        mouth_data = au_chunk[32:au_header.headerSize*2]

    au_header.markFlag = bool(mouth_data)
    au_header.headerSize = (sizeof(au_header) + sizeof(mouth_data)) // 2 # in units of uint16

    mouth_data_b = bytes(memoryview(mouth_data).cast('b'))
    print(f"{mouth_data=}")
    print(f"{au_header=}")

    newChunk = bytearray()
    newChunk.extend(memoryview(au_header).cast('B'))
    newChunk.extend(memoryview(mouth_data).cast('B'))
    newChunk.extend(memoryview(au_payload).cast('B'))
    print(f"Old chunk length {len(au_chunk)}")
    print(f"New chunk length {len(newChunk)}")
    with open("new.au", "wb") as f: f.write(newChunk)

    content = bytearray(content[:AUoffset])
    content.extend(memoryview(au_header).cast('B'))
    content.extend(memoryview(mouth_data).cast('B'))
    content.extend(memoryview(au_payload).cast('B'))

    if len(content) % 512 != 0:
        content.extend(b'\xff' * (512 - len(content) % 512))
    output_file.write(content)

if __name__ == '__main__':
    earpatch()

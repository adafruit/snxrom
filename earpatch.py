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

@click.command
@click.option("--au", type=click.File('rb'), default=None)
@click.option("--mouth", type=click.File('r'), default=None)
@click.option("--arbitrary-mouth", default=False, is_flag=True)
@click.option("--no-mouth", default=False, is_flag=True)
@click.argument("input-file", type=click.File('rb'))
@click.argument("output-file", type=click.File('wb'))
def earpatch(au, mouth, arbitrary_mouth, no_mouth, input_file, output_file):
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
    if mouth is not None:
        mouth_timings = json.load(mouth)
        mouth_data = snxrom.encodeMarkTable(mouth_timings)
    elif arbitrary_mouth:
        mouth_timings = arbitrary_mouth_data(au_header.sizeOfAudioBinary * 16 / au_header.bitRate / 10)
        mouth_data = bytearray(memoryview(snxrom.encodeMarkTable(mouth_timings)).cast('B'))
    elif no_mouth:
        mouth_data = b''
    else:
        mouth_data = au_chunk[32:au_header.headerSize*2]

    au_header.markFlag = bool(mouth_data)
    au_header.headerSize = (sizeof(au_header) + sizeof(mouth_data)) // 2 # in units of uint16

    mouth_data_b = bytes(memoryview(mouth_data).cast('B'))
    print(f"{len(mouth_data_b)=}")
    print(f"{list(memoryview(mouth_data).cast('H'))=} {len(mouth_data)}")
    print(f"{list(memoryview(mouth_data).cast('B'))=} {len(mouth_data)}")
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

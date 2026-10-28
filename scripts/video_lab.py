"""Experimental MP4 metadata matrix; preview by default, never overwrite sources.

All written identities, dates and coordinates are artificial teaching values.
Requires ExifTool and ffprobe on PATH. Not a batch library-repair command.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TIMES = [f'-QuickTime:{tag}=2020:06:01 04:34:56' for tag in (
    'CreateDate', 'ModifyDate', 'TrackCreateDate', 'TrackModifyDate',
    'MediaCreateDate', 'MediaModifyDate')]
LOCATION = ['-UserData:GPSCoordinates=39.9087 116.3975']
CASES = {
    'MODEL_KEYS.mp4': ['-Keys:Model=Keys Video Lab'],
    'MODEL_ANDROID.mp4': ['-Keys:AndroidModel=Android Video Lab'],
    'MODEL_OPLUS.mp4': ['-Keys:OplusProductModel=Oplus Video Lab'],
    'TIME_LOCATION.mp4': TIMES + LOCATION,
    'CUSTOM_VIDEO.mp4': ['-Keys:Model=Custom Video Camera',
                         '-Keys:AndroidModel=Custom Video Camera',
                         '-Keys:OplusProductModel=Custom Video Camera'] + TIMES + LOCATION,
}


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def packet_hash(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_packets',
        '-show_data_hash', 'sha256', '-show_entries',
        'packet=stream_index,pts,dts,duration,size,data_hash', '-of', 'json', str(path)],
        check=True, capture_output=True)
    packets = json.loads(result.stdout).get('packets', [])
    if not packets:
        raise ValueError('No media packets found')
    return hashlib.sha256(json.dumps(packets, sort_keys=True).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True, help='New directory only')
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    source = a.source.resolve(strict=True)
    output = a.output.resolve()
    if not source.is_file() or source.suffix.lower() != '.mp4':
        raise ValueError('Use an MP4 file')
    if output.exists():
        raise ValueError('Output directory already exists')
    if any('\n' in str(path) or '\r' in str(path) for path in (source, output)):
        raise ValueError('Newlines in paths are not supported')
    if not a.apply:
        print(json.dumps({'preview': True, 'artificial_values': True, 'cases': CASES}, indent=2))
        return
    original = file_hash(source)
    media = packet_hash(source)
    output.mkdir(parents=True, exist_ok=False)
    report = {'experimental': True, 'artificial_values': True,
              'source_sha256': original, 'samples': []}
    try:
        for name, changes in CASES.items():
            target = output / name
            arguments = ['-o', str(target), *changes, str(source)]
            # -config MUST be a real command-line option, not inside -@.
            subprocess.run(['exiftool', '-config', str(ROOT / 'profiles/oplus-video.config'),
                '-charset', 'filename=UTF8', '-@', '-'],
                input=('\n'.join(arguments) + '\n').encode('utf-8'),
                capture_output=True, check=True)
            unchanged = packet_hash(target) == media
            report['samples'].append({'file': name, 'requested': changes,
                'sha256': file_hash(target), 'packet_payload_and_timing_unchanged': unchanged})
            if not unchanged:
                raise ValueError('Media packet verification failed: ' + name)
    finally:
        report['source_unchanged'] = file_hash(source) == original
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['source_unchanged']:
        raise ValueError('Source changed during experiment')
    print('Created five test copies; packet payloads/timing and original hash verified.')
    print('Read back tags and verify gallery display separately; reports may contain private metadata.')


if __name__ == '__main__':
    main()

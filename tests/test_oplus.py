import json
import struct
import unittest
import xml.etree.ElementTree as ET

from oplus_metadata import build_trailer, parse_trailer, jpeg_end, inspect_bytes, make_motion_photo, headers, XMP_HEADER, NS


def minimal_jpeg():
    # Marker-level fixture: not used as a decoded photograph.
    return b'\xff\xd8\xff\xda\x00\x02\x01\x02\xff\x00\x03\xff\xd9'


class OplusStructureTests(unittest.TestCase):
    def test_camera_compatible_namespace_scope(self):
        video = struct.pack('>I',24)+b'ftypmp42'+b'\0'*12
        data = make_motion_photo(minimal_jpeg(), video, timestamp_us=1500000)
        packet = next(p[len(XMP_HEADER):] for m, _, _, p in headers(data)
                      if m == 0xe1 and p.startswith(XMP_HEADER))
        root_tag = packet.split(b'>', 1)[0]
        rdf_tag = packet.split(b'<rdf:RDF', 1)[1].split(b'>', 1)[0]
        desc_tag = packet.split(b'<rdf:Description', 1)[1].split(b'>', 1)[0]
        self.assertNotIn(b'xmlns:rdf=', root_tag)
        self.assertIn(b'xmlns:rdf=', rdf_tag)
        for prefix in ('GCamera', 'OpCamera', 'Container', 'Item'):
            declaration = ('xmlns:' + prefix + '=').encode()
            self.assertNotIn(declaration, root_tag)
            self.assertIn(declaration, desc_tag)
        tree = ET.fromstring(packet)
        desc = next(tree.iter('{' + NS['rdf'] + '}Description'))
        self.assertEqual(desc.attrib['{' + NS['GCamera'] + '}MotionPhotoPresentationTimestampUs'], '1500000')
        self.assertEqual(data[jpeg_end(data):], video)

    def test_jpeg_end_skips_thumbnail_and_stuffed_markers(self):
        image = minimal_jpeg()
        header = b'\xff\xe1\x00\x06xx\xff\xd9'
        data = image[:2] + header + image[2:] + b'not-image'
        self.assertEqual(jpeg_end(data), len(image) + len(header))

    def test_both_observed_footers_and_backward_offsets(self):
        for footer in (b'jxrs', b'wtmk'):
            trailer = build_trailer({'capture.mode': b'master\0',
                'capture.info.backup': b'{"originalFileName":"DEMO"}\0'}, footer)
            data = minimal_jpeg() + trailer
            result = parse_trailer(data)
            self.assertEqual(result['footer'], footer.decode())
            self.assertEqual(result['blocks']['capture.mode'], b'master\0')
            self.assertEqual(struct.unpack('>I', result['blocks']['private.emptyspace'])[0], len(trailer))
            self.assertEqual(result['start'], len(minimal_jpeg()))

    def test_rejects_out_of_bounds_index(self):
        index = json.dumps([{'name':'capture.mode','offset':999999,'length':7,'version':1}]).encode()+b'\0'
        data = minimal_jpeg()+index+b'jxrs'+struct.pack('<I',len(index)+8)
        with self.assertRaises(ValueError):
            parse_trailer(data)

    def test_inspection_redacts_backup_values(self):
        private = b'{"originalFileName":"PRIVATE-NAME","originalDateTakenMs":123456789}\0'
        data = minimal_jpeg()+build_trailer({'capture.mode':b'master\0','capture.info.backup':private})
        summary = inspect_bytes(data)
        rendered = json.dumps(summary)
        self.assertIn('capture.info.backup', rendered)
        self.assertNotIn('PRIVATE-NAME', rendered)
        self.assertNotIn('123456789', rendered)

    def test_motion_packet_references_new_video_and_container_sizes(self):
        video = struct.pack('>I',24)+b'ftypmp42'+b'\0'*12
        data = make_motion_photo(minimal_jpeg(),video,{'capture.mode':b'master\0'},0)
        summary = inspect_bytes(data)
        self.assertTrue(summary['motion_photo'])
        self.assertTrue(summary['motion_length_matches'])
        self.assertEqual(summary['primary_video_length'], len(video))
        self.assertEqual(parse_trailer(data)['blocks']['capture.mode'], b'master\0')


if __name__ == '__main__':
    unittest.main()

import io,json,hashlib,pathlib,plistlib,tempfile,unittest,zipfile
from unittest.mock import patch
import apollo_release_updater as u

def ipa(missing=False):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,bundle in u.EXPECTED.items():
            if missing and name=='ApolloIntentions':continue
            directory='Payload/Apollo.app'+('' if name=='Apollo' else '/PlugIns/'+name+'.appex')
            z.writestr(directory+'/Info.plist',plistlib.dumps({'CFBundleIdentifier':bundle}))
    return stream.getvalue()

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        (self.root/'original.ipa').write_bytes(ipa());(self.root/'release.json').write_text(json.dumps({'version':'3.8.5'}))
    def tearDown(self):self.tmp.cleanup()
    def release(self,v,data):
        return {'tag_name':'v1.15.11_'+v,'assets':[{'name':'Apollo-Reborn-'+v+'-GLASS.ipa','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'browser_download_url':'https://github.com/Apollo-Reborn/Apollo-Reborn/releases/download/tag/app.ipa'}]}
    def test_new_release_validated_promoted_and_not_downloaded_twice(self):
        data=ipa();r=self.release('3.9.0',data)
        with patch.object(u,'request',side_effect=[io.BytesIO(json.dumps(r).encode()),io.BytesIO(data)]) as req:
            self.assertTrue(u.update(self.root));self.assertEqual(req.call_count,2)
        with patch.object(u,'request',return_value=io.BytesIO(json.dumps(r).encode())) as req:
            self.assertFalse(u.update(self.root));self.assertEqual(req.call_count,1)
    def test_same_or_older_no_download(self):
        for v in ['3.8.5','3.8.4']:
            with patch.object(u,'request',return_value=io.BytesIO(json.dumps(self.release(v,ipa())).encode())) as req:
                self.assertFalse(u.update(self.root));self.assertEqual(req.call_count,1)
    def test_bad_checksum_and_missing_extension_keep_original(self):
        original=(self.root/'original.ipa').read_bytes()
        for data,bad in [(ipa(),True),(ipa(True),False)]:
            r=self.release('3.9.0',data)
            if bad:r['assets'][0]['digest']='sha256:'+'0'*64
            with patch.object(u,'request',side_effect=[io.BytesIO(json.dumps(r).encode()),io.BytesIO(data)]),self.assertLogs(level='ERROR'):
                self.assertFalse(u.update(self.root))
            self.assertEqual((self.root/'original.ipa').read_bytes(),original)
            self.assertEqual(list(self.root.glob('.release-*')),[])
    def test_prerelease_and_network_failure_keep_original(self):
        r=self.release('3.9.0',ipa());r['prerelease']=True
        with patch.object(u,'request',return_value=io.BytesIO(json.dumps(r).encode())),self.assertLogs(level='ERROR'):
            self.assertFalse(u.update(self.root))
        with patch.object(u,'request',side_effect=OSError('offline')),self.assertLogs(level='ERROR'):
            self.assertFalse(u.update(self.root))

if __name__=='__main__':unittest.main()

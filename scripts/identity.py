# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Runtime signing settings; never store user identities in source."""
import json,pathlib,re
OLD_ID='com.christianselig.Apollo'
OLD_GROUP='group.com.christianselig.apollo'
SUFFIXES={'Apollo':'','ApolloIntentions':'.ApolloIntentions','ApolloRebornWidgets':'.RebornWidgets',
'Apollofari':'.Apollofari','ApollofariLegacy':'.ApollofariLegacy','NotificationContentExtension':'.NotificationContentExtension',
'NotificationServiceExtension':'.NotificationServiceExtension','OpenInUIExtension':'.OpenInUIExtension'}
GROUP_TARGETS={'Apollo','ApolloIntentions','ApolloRebornWidgets','NotificationContentExtension','NotificationServiceExtension'}
def targets(bundle_id):return {name:bundle_id+suffix for name,suffix in SUFFIXES.items()}
def validate_identity(i):
    for key in ['team','certificate','device','udid','bundle_id','group']:
        if not isinstance(i.get(key),str) or not i[key].strip():raise ValueError('Missing signing setting: '+key)
    if not re.fullmatch(r'[A-Z0-9]{10}',i['team']):raise ValueError('Team ID must have ten letters/digits')
    if not re.fullmatch(r'[A-Fa-f0-9]{40}',i['certificate']):raise ValueError('Invalid signing certificate fingerprint')
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+){2,}',i['bundle_id']):raise ValueError('Invalid reverse-domain bundle ID')
    if not i['group'].startswith('group.') or not re.fullmatch(r'[A-Za-z0-9.-]+',i['group']) or len(i['group'].encode())!=len(OLD_GROUP.encode()):raise ValueError('App group must use exactly '+str(len(OLD_GROUP.encode()))+' ASCII bytes')
    return i
def load(path):return validate_identity(json.loads(pathlib.Path(path).read_text())['signing'])

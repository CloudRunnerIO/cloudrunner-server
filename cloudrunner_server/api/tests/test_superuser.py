from cloudrunner_server.api.tests import base


class SuperAdminTest(base.BaseRESTTestCase):

    def setUp(self):
        perm = self.permissions
        self.permissions = ['is_super_admin']
        super(SuperAdminTest, self).setUp()
        self.permissions = perm

    def test_list_orgs(self):
        resp = self.app.get('/rest/manage/orgs/',
                            headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                     'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200)
        resp_json = resp.json

        for org in resp_json['orgs']:
            org.pop('created_at')
            uuid = org.pop('uid')
            self.assertEqual(len(uuid), 32)
        self.assertContains(resp_json['orgs'],
                            {"enabled": True,
                             "name": "MyOrg",
                             "tier_id": 2})
        self.assertContains(resp_json['orgs'],
                            {"enabled": False,
                             "name": "MyOrg2",
                             "tier_id": 1})

    def test_create_org(self):
        resp = self.app.post('/rest/manage/orgs',
                             "org=OrgZ&tier=Free",
                             headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                      'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}}, resp.body)

    def test_activate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'status=1',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def test_deactivate_org(self):
        resp = self.app.patch('/rest/manage/orgs/MyOrg2',
                              'status=0',
                              headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                       'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

    def test_delete_org(self):
        resp = self.app.delete('/rest/manage/orgs/MyOrg2',
                               headers={'Cr-Token': 'PREDEFINED_TOKEN',
                                        'Cr-User': 'testuser'})
        self.assertEqual(resp.status_int, 200, resp.status_int)
        resp_json = resp.json

        self.assertEqual(resp_json, {"success": {"status": "ok"}},
                         resp.body)

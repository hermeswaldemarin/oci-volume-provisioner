#!/usr/bin/env python

# Copyright (c) 2018 Oracle and/or its affiliates. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import time
import utils
from yaml_utils import PopulateYaml
from vol_provisioner_system_test import VolumeProvisionerSystemTestInterface

class FSSSystemTests(VolumeProvisionerSystemTestInterface):

    STORAGE_CLAIM_WITH_SUBNET_ID = "templates/example-storage-class-fss-subnet.template"
    STORAGE_CLAIM_WITH_MNT_ID = "templates/example-storage-class-fss-mnt.template"
    STORAGE_CLAIM_EMPTY = "templates/example-storage-class-fss-empty.template"
    FSS_CLAIM = "templates/example-claim-fss.template"
    MNT_TARGET_OCID = "MNT_TARGET_OCID"
    SUBNET_OCID = "SUBNET_OCID"
    KUBERNETES_RESOURCES = ["../../dist/oci-volume-provisioner-fss.yaml",
                            "../../dist/oci-volume-provisioner-rbac.yaml"]
    TEST_SC_FILES = {"mntid": STORAGE_CLAIM_WITH_MNT_ID, "empty": STORAGE_CLAIM_EMPTY}
    CM_FSS = ""

    def __init__(self, subnet_ocid=None, mnt_target_ocid=None, test_id=None, setup=False, check_oci=False, canaryMetrics=None):
        super(FSSSystemTests, self).__init__(test_id=test_id, setup=setup, check_oci=check_oci,
                                             k8Resources=self.KUBERNETES_RESOURCES, canaryMetrics=canaryMetrics)
        self._subnet_ocid = subnet_ocid
        self._mnt_target_ocid = mnt_target_ocid
        self._scFile = self.STORAGE_CLAIM_WITH_SUBNET_ID

    def run(self):
        super(FSSSystemTests, self).run()
        if self._check_oci: # Do not run tests in the validate-test-image stage
            utils.log("Running system test: Create volume with FSS", as_banner=True)
            for _testScName, _testScFile in self.TEST_SC_FILES.iteritems():
                # Not testing the creation of a mount target, as all mount targets on the system will have
                # to be removed
                self._testCreateVolumeFromStorageClass(_testScFile)
                # Wait for 5 seconds to allow the previous pod to be deleted
                time.sleep(5)

    def _testCreateVolumeFromStorageClass(self, scFile):
        '''Test creating a volume based on provided storage class
        @type scFile: Path for storage class config file
        @param scFile: C{Str}'''
        utils.log("Testing for sc: %s" % scFile, as_banner=True)
        _storageClassFile = PopulateYaml(self._scFile, self._test_id, mount_target_ocid=self._mnt_target_ocid,
                                         subnet_ocid=self._subnet_ocid).generateFile()
        # Delete any previously existing storage classes with the same name
        utils.kubectl("delete -f " + _storageClassFile, exit_on_error=False)
        # Create storage class yaml file
        _storageClassFile = PopulateYaml(self._scFile, self._test_id, mount_target_ocid=self._mnt_target_ocid,
                                         subnet_ocid=self._subnet_ocid).generateFile()
        utils.kubectl("create -f " + _storageClassFile, exit_on_error=False)
        self._testSuccess = self._test_create_volume(PopulateYaml(self.FSS_CLAIM, self._test_id, region=self._region).generateFile(),
                                                     "demooci-fss-" + self._test_id, availability_domain=self.DEFAULT_AVAILABILITY_DOMAIN,
                                                     storageType=self.FS_STORAGE, verify_func=self._volume_from_fss_dynamic_check, canaryMetricName=self.CM_FSS)
        self._checkTestSuccess()

    def _volume_from_fss_dynamic_check(self, availability_domain, volume, file_name='hello.txt'):
        '''Verify whether the file system is attached to the pod and can be written to
        @param test_id: Test id to use for creating components
        @type test_id: C{Str}
        @param availability_domain: Availability domain to create resource in
        @type availability_domain: C{Str}
        @param volume: Name of volume to verify
        @type volume: C{Str}
        @param file_name: Name of file to do checks for
        @type file_name: C{Str}'''
        _ocid = volume.split('.')
        _ocid = _ocid[-1]
        _rc_name, _rc_config = self._create_rc_or_pod("templates/example-pod-fss.template",
                                                      availability_domain, _ocid)
        utils.log("Does the file from the previous backup exist?")
        stdout = utils.kubectl("exec " + _rc_name + " -- ls /usr/share/nginx/html")
        if file_name not in stdout.split("\n"):
            utils.log("Error: Failed to find file %s in mounted volume" % file_name)
        utils.log("Deleting the replication controller (deletes the single nginx pod).")
        utils.kubectl("delete -f " + _rc_config)

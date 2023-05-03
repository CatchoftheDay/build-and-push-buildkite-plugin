import os
from unittest import mock, main, TestCase

from pipeline import create_build_step, create_oci_manifest_step, create_scan_step, process_env_to_config, PLUGIN_ENV_PREFIX


class TestPipelineGeneration(TestCase):
    config = {
        'image_name': 'testcase',
        'image_tag': '1234567890',
        'build_args': ['arg1=42', 'arg2', 'GITHUB_TOKEN'],
        'dockerfile_path': 'Dockerfile',
        'context_path': '.',
        'build_arm': True,
        'build_x86': False,
        'scan_image': True,
        'group_key': 'build-and-push',
        'additional_tag': None,
        'always_pull': True,
        'composer_cache': False,
        'npm_cache': False,
    }

    RUNTIME_ENVS = {
        f'{PLUGIN_ENV_PREFIX}DOCKERFILE_PATH': 'Dockerfile',
        f'{PLUGIN_ENV_PREFIX}CONTEXT_PATH': '.',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARGS': 'arg1=42,arg2',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARM': 'true',
        f'{PLUGIN_ENV_PREFIX}BUILD_X86': 'false',
        f'{PLUGIN_ENV_PREFIX}ARM_BUILD_REQUIRED': 'true',
        'BUILDKITE_COMMIT': '123456789010',
        'BUILDKITE_PIPELINE_NAME': 'testcase',
        'BUILDKITE_BUILD_NUMBER': '110',
    }

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    def test_process_env_to_config(this):
        config = process_env_to_config()

        this.assertEqual(config, this.config)

    def test_create_build_step(this):
        platform = 'arm'
        agent = 'docker-arm'

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step['label'], ':docker: Build and push arm image')
        this.assertEqual(step['agents'], {'queue': 'docker-arm'})
        this.assertEqual(step['command'], [
            'docker pull 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 || true',
            'docker buildx build --push --pull --ssh default --cache-from 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN   --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .',
        ])
        this.assertEqual(step['env'], {'DOCKER_BUILDKIT': '1'})
        this.assertEqual(step['key'], 'build-and-push-build-push-arm')

    def test_create_manifest_step(this):
        step = create_oci_manifest_step(this.config)

        this.assertEqual(step['command'], [
            'docker manifest create 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm',
            'docker manifest push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890',
        ])

        this.assertEqual(step['depends_on'], ['build-and-push-build-push-arm'])

        this.assertNotIn('agent', step)

    def test_create_manifest_step_multi_arch(this):
        multi_arch_config = this.config.copy()
        multi_arch_config['build_x86'] = True

        step = create_oci_manifest_step(multi_arch_config)

        this.assertEqual(step['command'], [
            'docker manifest create 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86',
            'docker manifest push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890',
        ])

        this.assertEqual(step['depends_on'], ['build-and-push-build-push-arm', 'build-and-push-build-push-x86'])

        this.assertNotIn('agent', step)

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    def test_create_scan_step(this):
        step = create_scan_step(this.config)

        this.assertEqual(step['command'], [
            'docker pull 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890',
            'curl -o wizcli https://wizcli.app.wiz.io/latest/wizcli',
            'chmod +x ./wizcli',
            './wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET',
            f'./wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 --tag pipeline=testcase --tag pipeline_run=110',
        ])

        this.assertEqual(step['depends_on'], 'build-and-push-manifest')

if __name__ == '__main__':
    main()

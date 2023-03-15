import os
from unittest import mock, main, TestCase

from pipeline import create_build_step, create_manifest_step, create_scan_step, process_env_to_config, PLUGIN_ENV_PREFIX


class TestPipelineGeneration(TestCase):
    config = {
        'image_name': 'testcase',
        'image_tag': '1234567890',
        'build_args': ['arg1=42', 'arg2', 'GITHUB_TOKEN'],
        'dockerfile': 'Dockerfile',
        'dockerfile_path': '.',
        'build_arm': True,
        'build_x86': False,
        'scan_images': True,
    }

    RUNTIME_ENVS = {
        f'{PLUGIN_ENV_PREFIX}DOCKERFILE': 'Dockerfile',
        f'{PLUGIN_ENV_PREFIX}DOCKERFILE_PATH': '.',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARGS': 'arg1=42,arg2',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARM': 'true',
        f'{PLUGIN_ENV_PREFIX}BUILD_X86': 'false',
        f'{PLUGIN_ENV_PREFIX}ARM_BUILD_REQUIRED': 'true',
        'BUILDKITE_COMMIT': '123456789010',
        'BUILDKITE_PIPELINE_NAME': 'testcase',
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
            'docker buildx build --push --ssh default=$$SSH_AUTH_SOCK --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890-arm -f Dockerfile .',
        ])
        this.assertEqual(step['env'], {'DOCKER_BUILDKIT': '1'})
        this.assertEqual(step['key'], 'build-push-arm')

    def test_create_manifest_step(this):
        step = create_manifest_step(this.config)

        this.assertEqual(step['command'], [
            'docker manifest create 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890-arm',
            'docker manifest push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890',
            'aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids TAG="1234567890-arm"',
        ])

        this.assertEqual(step['depends_on'], ['build-push-arm'])

        this.assertNotIn('agent', step)

    def test_create_manifest_step_multi_arch(this):
        multi_arch_config = this.config.copy()
        multi_arch_config['build_x86'] = True

        step = create_manifest_step(multi_arch_config)

        this.assertEqual(step['command'], [
            'docker manifest create 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890-x86',
            'docker manifest push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890',
            'aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids TAG="1234567890-arm"',
            'aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids TAG="1234567890-x86"',
        ])

        this.assertEqual(step['depends_on'], ['build-push-arm', 'build-push-x86'])

        this.assertNotIn('agent', step)

    def test_create_scan_step(this):
        step = create_scan_step(this.config)

        this.assertEqual(step['command'], [
            'if [[ -z "$${RAPID7_API_KEY}" ]]; then echo "A Rapid7 API key needs to be added to your build secrets as RAPID7_API_KEY"; exit 1; fi',
            'docker save 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 -o "testcase.tar"',
            'docker run --rm -v $(pwd)/docker_image.tar:/docker_image.tar rapid7/container-image-scanner:latest -f=/docker_image.tar -k=$$RAPID7_API_KEY -r=au --buildId "1234567890" --buildName testcase',
        ])

        this.assertEqual(step['depends_on'], 'create-container-manifest')

if __name__ == '__main__':
    main()

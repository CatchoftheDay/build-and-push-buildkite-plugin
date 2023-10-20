import os
import time
from unittest import mock, main, TestCase

from pipeline import create_build_step, create_oci_manifest_step, process_env_to_config, PLUGIN_ENV_PREFIX, BUILDKIT_VERSION

BUILD_TIME = int(time.time())

class TestPipelineGeneration(TestCase):
    config = {
        'image_name': 'testcase',
        'image_tag': '1234567890',
        # Setting BUILD_DATE like this is likely to cause issues at some point if the config generation tests takes longer than 1 second
        'build_args': ['arg1=42', 'arg2', 'GITHUB_TOKEN', 'BUILDKITE_COMMIT', 'BUILDKITE_JOB_ID', f'BUILD_DATE={BUILD_TIME}'],
        'dockerfile_path': 'Dockerfile',
        'context_path': '.',
        'build_arm': True,
        'build_x86': False,
        'push_branches': [],
        'scan_image': True,
        'group_key': 'build-and-push',
        'additional_tag': None,
        'always_pull': True,
        'composer_cache': False,
        'npm_cache': False,
        'yarn_cache': False,
        'fully_qualified_image_name': '362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase',
        'push_to_ecr': True,
        'repository_namespace': 'catch',
    }

    maxDiff = None

    RUNTIME_ENVS = {
        f'{PLUGIN_ENV_PREFIX}DOCKERFILE_PATH': 'Dockerfile',
        f'{PLUGIN_ENV_PREFIX}CONTEXT_PATH': '.',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARGS': 'arg1=42,arg2',
        f'{PLUGIN_ENV_PREFIX}BUILD_ARM': 'true',
        f'{PLUGIN_ENV_PREFIX}BUILD_X86': 'false',
        f'{PLUGIN_ENV_PREFIX}ARM_BUILD_REQUIRED': 'true',
        'BUILDKITE_COMMIT': '123456789010',
        'BUILDKITE_BRANCH': 'main',
        'BUILDKITE_PIPELINE_NAME': 'testcase',
        'BUILDKITE_BUILD_NUMBER': '110',
        'WIZ_CLIENT_ID': 'wiz-client-id',
        'WIZ_CLIENT_SECRET': 'wiz-client-secret',
    }

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_process_env_to_config(this):
        config = process_env_to_config()

        this.assertEqual(config, this.config)

    @mock.patch.dict(os.environ, dict({f'{PLUGIN_ENV_PREFIX}PUSH_BRANCHES': 'testing'}, **RUNTIME_ENVS))
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_process_env_to_config_no_push_branch(this):
        config = process_env_to_config()

        no_config = this.config.copy()
        no_config['push_branches'] = ['testing']
        no_config['push_to_ecr'] = False

        this.assertEqual(config, no_config)

    @mock.patch.dict(os.environ, dict({f'{PLUGIN_ENV_PREFIX}PUSH_BRANCHES': 'testing,main'}, **RUNTIME_ENVS))
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_process_env_to_config_no_push_branch(this):
        config = process_env_to_config()

        yes_config = this.config.copy()
        yes_config['push_branches'] = ['testing', 'main']

        this.assertEqual(config, yes_config)

    @mock.patch.dict(os.environ, dict({f'{PLUGIN_ENV_PREFIX}REPOSITORY_NAMESPACE': 'docker.io'}, **RUNTIME_ENVS))
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_process_env_to_config_different_namespace(this):
        config = process_env_to_config()

        ns_config = this.config.copy()
        ns_config['fully_qualified_image_name'] = '362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/docker.io/testcase'
        ns_config['repository_namespace'] = 'docker.io'

        this.assertEqual(config, ns_config)


    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_create_build_step_push(this):
        platform = 'arm'
        agent = 'docker-arm'

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step['label'], ':docker: Build and push arm image')
        this.assertEqual(step['agents'], {'queue': 'docker-arm'})
        this.maxDiff = None
        this.assertEqual(step['command'], [
            f'docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}',
            f'docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .',
            'curl -o wizcli https://wizcli.app.wiz.io/latest/wizcli-linux-arm64',
            'chmod +x ./wizcli',
            './wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET',
            './wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=0',
            'if [[ $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style info --context arm-image-security-scan; else echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context arm-image-security-scan; fi',
            'test $$SCAN_STATUS -eq 0 || exit 1',
            'docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm'
        ])

        this.assertEqual(step['env'], {'DOCKER_BUILDKIT': '1'})
        this.assertEqual(step['key'], 'build-and-push-build-push-arm')
    
    @mock.patch.dict(os.environ, dict({f'BUILDKITE_TAG': 'v1.0.0', 'BUILDKITE_BRANCH': 'v1.0.0'}, **RUNTIME_ENVS))
    @mock.patch('pipeline.CURRENT_BRANCH', 'v1.0.0')
    @mock.patch('pipeline.CURRENT_TAG', 'v1.0.0')
    def test_create_build_step_push_tags(this):
        platform = 'arm'
        agent = 'docker-arm'

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step['label'], ':docker: Build and push arm image')
        this.assertEqual(step['agents'], {'queue': 'docker-arm'})
        this.maxDiff = None
        this.assertEqual(step['command'], [
            f'docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}',
            f'docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:master --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:v1.0.0 --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .',
            'curl -o wizcli https://wizcli.app.wiz.io/latest/wizcli-linux-arm64',
            'chmod +x ./wizcli',
            './wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET',
            './wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=0',
            'if [[ $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style info --context arm-image-security-scan; else echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context arm-image-security-scan; fi',
            'test $$SCAN_STATUS -eq 0 || exit 1',
            'docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm'
        ])

        this.assertEqual(step['env'], {'DOCKER_BUILDKIT': '1'})
        this.assertEqual(step['key'], 'build-and-push-build-push-arm')

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_create_build_step_no_push(this):
        platform = 'arm'
        agent = 'docker-arm'
        
        config = this.config.copy()
        config['push_to_ecr'] = False
        step = create_build_step(platform, agent, config)

        this.assertEqual(step['label'], ':docker: Build arm image')
        this.assertEqual(step['agents'], {'queue': 'docker-arm'})
        this.maxDiff = None
        this.assertEqual(step['command'], [
            f'docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}',
            f'docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .',
            'curl -o wizcli https://wizcli.app.wiz.io/latest/wizcli-linux-arm64',
            'chmod +x ./wizcli',
            './wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET',
            './wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=0',
            'if [[ $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style info --context arm-image-security-scan; else echo -e "**Container scan report (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context arm-image-security-scan; fi',
            'test $$SCAN_STATUS -eq 0 || exit 1',
            'echo "Not pushing to ECR as branch not listed in push-branches"',
        ])

        this.assertEqual(step['env'], {'DOCKER_BUILDKIT': '1'})
        this.assertEqual(step['key'], 'build-and-push-build-push-arm')
    
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_create_manifest_step(this):
        step = create_oci_manifest_step(this.config)

        this.assertEqual(step['command'], [
            'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm',
            f'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:main 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm',
        ])

        this.assertEqual(step['depends_on'], ['build-and-push-build-push-arm'])

        this.assertNotIn('agent', step)

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch('pipeline.CURRENT_BRANCH', 'main')
    @mock.patch('pipeline.CURRENT_TAG', '')
    def test_create_manifest_step_multi_arch(this):
        multi_arch_config = this.config.copy()
        multi_arch_config['build_x86'] = True

        step = create_oci_manifest_step(multi_arch_config)

        this.assertEqual(step['command'], [
            'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86',
            f'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:main 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86',
        ])

        this.assertEqual(step['depends_on'], ['build-and-push-build-push-arm', 'build-and-push-build-push-x86'])

        this.assertNotIn('agent', step)

    @mock.patch.dict(os.environ, dict({f'BUILDKITE_TAG': 'v1.0.0', 'BUILDKITE_BRANCH': 'v1.0.0'}, **RUNTIME_ENVS))
    @mock.patch('pipeline.CURRENT_BRANCH', 'v1.0.0')
    @mock.patch('pipeline.CURRENT_TAG', 'v1.0.0')
    def test_create_manifest_step_multi_arch_tag(this):
        multi_arch_config = this.config.copy()
        multi_arch_config['build_x86'] = True

        step = create_oci_manifest_step(multi_arch_config)

        this.assertEqual(step['command'], [
            'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86',
            f'docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:v1.0.0 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86',
        ])

        this.assertEqual(step['depends_on'], ['build-and-push-build-push-arm', 'build-and-push-build-push-x86'])

        this.assertNotIn('agent', step)


if __name__ == '__main__':
    main()

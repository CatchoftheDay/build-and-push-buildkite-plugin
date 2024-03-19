import os
import json
import time
from unittest import mock, main, TestCase

from pipeline import (
    create_build_step,
    create_oci_manifest_step,
    process_config,
    BUILDKIT_VERSION,
)

BUILD_TIME = int(time.time())


class TestPipelineGeneration(TestCase):
    config = {
        "image-name": "testcase",
        "image-tag": "1234567890",
        "mutate-image-tag": False,
        # Setting BUILD_DATE like this is likely to cause issues at some point if the config generation tests takes longer than 1 second
        "build-args": [
            "arg1=42",
            "arg2",
            "GITHUB_TOKEN",
            "BUILDKITE_COMMIT",
            "BUILDKITE_JOB_ID",
            f"BUILD_DATE={BUILD_TIME}",
        ],
        "dockerfile-path": "Dockerfile",
        "context-path": ".",
        "build-arm": True,
        "build-x86": False,
        "push-branches": [],
        "scan-image": True,
        "group-key": "build-and-push",
        "additional-tag": None,
        "always-pull": True,
        "composer-cache": False,
        "npm-cache": False,
        "yarn-cache": False,
        "fully-qualified-image-name": "362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase",
        "push-to-ecr": True,
        "repository-namespace": "catch",
    }

    maxDiff = None

    BUILDKITE_PLUGIN_CONFIGURATION = {
        "dockerfile-path": "Dockerfile",
        "context-path": ".",
        "build-args": "arg1=42,arg2",
        "build-arm": "true",
        "build-x86": "false",
    }

    RUNTIME_ENVS = {
        "BUILDKITE_PLUGIN_CONFIGURATION": json.dumps(BUILDKITE_PLUGIN_CONFIGURATION),
        "BUILDKITE_COMMIT": "123456789010",
        "BUILDKITE_BRANCH": "main",
        "BUILDKITE_PIPELINE_NAME": "testcase",
        "BUILDKITE_BUILD_NUMBER": "110",
        "WIZ_CLIENT_ID": "wiz-client-id",
        "WIZ_CLIENT_SECRET": "wiz-client-secret",
    }

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_process_config(this):
        config = process_config()

        this.assertEqual(config, this.config)

    @mock.patch.dict(
        os.environ,
        RUNTIME_ENVS | { "BUILDKITE_PLUGIN_CONFIGURATION": json.dumps({**BUILDKITE_PLUGIN_CONFIGURATION | {'push-branches': "testing"}})}
    )
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_process_config_no_push_branch(this):
        config = process_config()

        no_config = this.config.copy()
        no_config["push-branches"] = ["testing"]
        no_config["push-to-ecr"] = False

        this.assertEqual(config, no_config)

    @mock.patch.dict(
        os.environ,
        RUNTIME_ENVS | { "BUILDKITE_PLUGIN_CONFIGURATION": json.dumps({**BUILDKITE_PLUGIN_CONFIGURATION | {'push-branches': "testing,main"}})}
    )
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_process_config_no_push_branch(this):
        config = process_config()

        yes_config = this.config.copy()
        yes_config["push-branches"] = ["testing", "main"]

        this.assertEqual(config, yes_config)


    @mock.patch.dict(
        os.environ,
        RUNTIME_ENVS | { "BUILDKITE_PLUGIN_CONFIGURATION": json.dumps({**BUILDKITE_PLUGIN_CONFIGURATION | {'repository-namespace': "docker.io"}})}
    )
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_process_config_different_namespace(this):
        config = process_config()

        ns_config = this.config.copy()
        ns_config[
            "fully-qualified-image-name"
        ] = "362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/docker.io/testcase"
        ns_config["repository-namespace"] = "docker.io"

        this.assertEqual(config, ns_config)

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_build_step_push(this):
        platform = "arm"
        agent = "docker-arm"

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step["label"], ":docker: Build and push arm image")
        this.assertEqual(step["agents"], {"queue": "docker-arm"})
        this.maxDiff = None
        this.assertEqual(
            step["command"],
            [
                f"docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}",
                f"docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .",
                "wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET",
                'wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=$${PIPESTATUS[0]}',
                'if [[ ! $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report [testcase:1234567890] (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context testcase-1234567890-arm-security-scan; fi',
                "docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["env"], {"DOCKER_BUILDKIT": "1"})
        this.assertEqual(step["key"], "build-and-push-build-push-arm")

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_build_step_push_mutate_tags(this):
        platform = "arm"
        agent = "docker-arm"

        config = this.config.copy()
        config["mutate-image-tag"] = True
        step = create_oci_manifest_step(config)

        step = create_build_step(platform, agent, config)

        this.assertEqual(step["label"], ":docker: Build and push arm image")
        this.assertEqual(step["agents"], {"queue": "docker-arm"})
        this.maxDiff = None
        this.assertEqual(
            step["command"],
            [
                f"docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}",
                f"docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .",
                "wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET",
                'wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=$${PIPESTATUS[0]}',
                'if [[ ! $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report [testcase:1234567890] (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context testcase-1234567890-arm-security-scan; fi',
                "docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["env"], {"DOCKER_BUILDKIT": "1"})
        this.assertEqual(step["key"], "build-and-push-build-push-arm")

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    @mock.patch("pipeline.BLOCK_ON_CONTAINER_SCAN", True)
    def test_create_build_step_push_scan_block(this):
        platform = "arm"
        agent = "docker-arm"

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step["label"], ":docker: Build and push arm image")
        this.assertEqual(step["agents"], {"queue": "docker-arm"})
        this.maxDiff = None
        this.assertEqual(
            step["command"],
            [
                f"docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}",
                f"docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .",
                "wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET",
                'wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=$${PIPESTATUS[0]}',
                'if [[ ! $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report [testcase:1234567890] (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context testcase-1234567890-arm-security-scan; fi',
                "if [[ ! $$SCAN_STATUS -eq 0 ]]; then exit $$SCAN_STATUS; fi",
                "docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["env"], {"DOCKER_BUILDKIT": "1"})
        this.assertEqual(step["key"], "build-and-push-build-push-arm")

    @mock.patch.dict(
        os.environ,
        RUNTIME_ENVS | { "BUILDKITE_TAG": "v1.0.0", "BUILDKITE_BRANCH": "v1.0.0" }
    )
    @mock.patch("pipeline.CURRENT_BRANCH", "v1.0.0")
    @mock.patch("pipeline.CURRENT_TAG", "v1.0.0")
    def test_create_build_step_push_tags(this):
        platform = "arm"
        agent = "docker-arm"

        step = create_build_step(platform, agent, this.config)

        this.assertEqual(step["label"], ":docker: Build and push arm image")
        this.assertEqual(step["agents"], {"queue": "docker-arm"})
        this.maxDiff = None
        this.assertEqual(
            step["command"],
            [
                f"docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}",
                f"docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_master --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_v1.0.0 --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .",
                "wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET",
                'wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=$${PIPESTATUS[0]}',
                'if [[ ! $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report [testcase:1234567890] (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context testcase-1234567890-arm-security-scan; fi',
                "docker image push 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["env"], {"DOCKER_BUILDKIT": "1"})
        this.assertEqual(step["key"], "build-and-push-build-push-arm")

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_build_step_no_push(this):
        platform = "arm"
        agent = "docker-arm"

        config = this.config.copy()
        config["push-to-ecr"] = False
        step = create_build_step(platform, agent, config)

        this.assertEqual(step["label"], ":docker: Build arm image")
        this.assertEqual(step["agents"], {"queue": "docker-arm"})
        this.maxDiff = None
        this.assertEqual(
            step["command"],
            [
                f"docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}",
                f"docker buildx build --load --pull --ssh default  --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_1234567890 --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main --cache-from type=registry,ref=362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_master --build-arg arg1=42 --build-arg arg2 --build-arg GITHUB_TOKEN --build-arg BUILDKITE_COMMIT --build-arg BUILDKITE_JOB_ID --build-arg BUILD_DATE={BUILD_TIME}    --tag 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -f Dockerfile .",
                "wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET",
                'wizcli docker scan --image 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm -p "Container Scanning" -p "Secret Scanning" --tag pipeline=testcase --tag architecture=arm --tag pipeline_run=110 > out 2>&1 | true; SCAN_STATUS=$${PIPESTATUS[0]}',
                'if [[ ! $$SCAN_STATUS -eq 0 ]]; then echo -e "**Container scan report [testcase:1234567890] (arm)**\n\n<details><summary></summary>\n\n\\`\\`\\`term\n$(cat out**)\\`\\`\\`\n\n</details>" | buildkite-agent annotate --style error --context testcase-1234567890-arm-security-scan; fi',
                'echo "Not pushing to ECR as branch not listed in push-branches"',
            ],
        )

        this.assertEqual(step["env"], {"DOCKER_BUILDKIT": "1"})
        this.assertEqual(step["key"], "build-and-push-build-push-arm")

    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_manifest_step(this):
        step = create_oci_manifest_step(this.config)

        this.assertEqual(
            step["command"],
            [
                "docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
                "aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids imageTag=cache_main || true",
                f"docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["depends_on"], ["build-and-push-build-push-arm"])

        this.assertNotIn("agent", step)

    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_manifest_step_mutate_tags(this):
        config = this.config.copy()
        config["mutate-image-tag"] = True
        step = create_oci_manifest_step(config)

        this.assertEqual(
            step["command"],
            [
                "aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids imageTag=1234567890 || true",
                "docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
                "aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids imageTag=cache_main || true",
                f"docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm",
            ],
        )

        this.assertEqual(step["depends_on"], ["build-and-push-build-push-arm"])

        this.assertNotIn("agent", step)

    @mock.patch.dict(os.environ, RUNTIME_ENVS)
    @mock.patch("pipeline.CURRENT_BRANCH", "main")
    @mock.patch("pipeline.CURRENT_TAG", "")
    def test_create_manifest_step_multi_arch(this):
        multi_arch_config = this.config.copy()
        multi_arch_config["build-x86"] = True

        step = create_oci_manifest_step(multi_arch_config)

        this.assertEqual(
            step["command"],
            [
                "docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86",
                "aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids imageTag=cache_main || true",
                f"docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_main 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86",
            ],
        )

        this.assertEqual(
            step["depends_on"],
            ["build-and-push-build-push-arm", "build-and-push-build-push-x86"],
        )

        this.assertNotIn("agent", step)

    @mock.patch.dict(
        os.environ,
        RUNTIME_ENVS | { "BUILDKITE_TAG": "v1.0.0", "BUILDKITE_BRANCH": "v1.0.0" }
    )
    @mock.patch(
        "pipeline.CURRENT_BRANCH", "v1.0.0"
    )  # This is due to a BK "bug" where the branch is set to the tag name
    @mock.patch("pipeline.CURRENT_TAG", "v1.0.0")
    def test_create_manifest_step_multi_arch_tag(this):
        multi_arch_config = this.config.copy()
        multi_arch_config["build-x86"] = True

        step = create_oci_manifest_step(multi_arch_config)

        this.assertEqual(
            step["command"],
            [
                "docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:1234567890 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86",
                "aws ecr batch-delete-image --registry-id 362995399210 --repository-name catch/testcase --image-ids imageTag=cache_v1.0.0 || true",
                f"docker buildx imagetools create -t 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:cache_v1.0.0 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-arm 362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/testcase:multi-platform-1234567890-x86",
            ],
        )

        this.assertEqual(
            step["depends_on"],
            ["build-and-push-build-push-arm", "build-and-push-build-push-x86"],
        )

        this.assertNotIn("agent", step)


if __name__ == "__main__":
    main()

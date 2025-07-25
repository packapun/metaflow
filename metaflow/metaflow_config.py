import os
import sys
import types

from metaflow.exception import MetaflowException
from metaflow.metaflow_config_funcs import from_conf, get_validate_choice_fn

# Disable multithreading security on MacOS
if sys.platform == "darwin":
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

## NOTE: Just like Click's auto_envar_prefix `METAFLOW` (see in cli.py), all environment
## variables here are also named METAFLOW_XXX. So, for example, in the statement:
## `DEFAULT_DATASTORE = from_conf("DEFAULT_DATASTORE", "local")`, to override the default
## value, either set `METAFLOW_DEFAULT_DATASTORE` in your configuration file or set
## an environment variable called `METAFLOW_DEFAULT_DATASTORE`

##
# Constants (NOTE: these need to live before any from_conf)
##

# Path to the local directory to store artifacts for 'local' datastore.
DATASTORE_LOCAL_DIR = ".metaflow"

# Local configuration file (in .metaflow) containing overrides per-project
LOCAL_CONFIG_FILE = "config.json"

###
# Default configuration
###

DEFAULT_DATASTORE = from_conf("DEFAULT_DATASTORE", "local")
DEFAULT_ENVIRONMENT = from_conf("DEFAULT_ENVIRONMENT", "local")
DEFAULT_EVENT_LOGGER = from_conf("DEFAULT_EVENT_LOGGER", "nullSidecarLogger")
DEFAULT_METADATA = from_conf("DEFAULT_METADATA", "local")
DEFAULT_MONITOR = from_conf("DEFAULT_MONITOR", "nullSidecarMonitor")
DEFAULT_PACKAGE_SUFFIXES = from_conf("DEFAULT_PACKAGE_SUFFIXES", ".py,.R,.RDS")
DEFAULT_AWS_CLIENT_PROVIDER = from_conf("DEFAULT_AWS_CLIENT_PROVIDER", "boto3")
DEFAULT_AZURE_CLIENT_PROVIDER = from_conf(
    "DEFAULT_AZURE_CLIENT_PROVIDER", "azure-default"
)
DEFAULT_GCP_CLIENT_PROVIDER = from_conf("DEFAULT_GCP_CLIENT_PROVIDER", "gcp-default")
DEFAULT_SECRETS_BACKEND_TYPE = from_conf("DEFAULT_SECRETS_BACKEND_TYPE")
DEFAULT_SECRETS_ROLE = from_conf("DEFAULT_SECRETS_ROLE")

DEFAULT_FROM_DEPLOYMENT_IMPL = from_conf(
    "DEFAULT_FROM_DEPLOYMENT_IMPL", "argo-workflows"
)

###
# User configuration
###
USER = from_conf("USER")


###
# Datastore configuration
###
DATASTORE_SYSROOT_LOCAL = from_conf("DATASTORE_SYSROOT_LOCAL")
# S3 bucket and prefix to store artifacts for 's3' datastore.
DATASTORE_SYSROOT_S3 = from_conf("DATASTORE_SYSROOT_S3")
# Azure Blob Storage container and blob prefix
DATASTORE_SYSROOT_AZURE = from_conf("DATASTORE_SYSROOT_AZURE")
DATASTORE_SYSROOT_GS = from_conf("DATASTORE_SYSROOT_GS")
# GS bucket and prefix to store artifacts for 'gs' datastore


###
# Datastore local cache
###

# Path to the client cache
CLIENT_CACHE_PATH = from_conf("CLIENT_CACHE_PATH", "/tmp/metaflow_client")
# Maximum size (in bytes) of the cache
CLIENT_CACHE_MAX_SIZE = from_conf("CLIENT_CACHE_MAX_SIZE", 10000)
# Maximum number of cached Flow and TaskDatastores in the cache
CLIENT_CACHE_MAX_FLOWDATASTORE_COUNT = from_conf(
    "CLIENT_CACHE_MAX_FLOWDATASTORE_COUNT", 50
)
CLIENT_CACHE_MAX_TASKDATASTORE_COUNT = from_conf(
    "CLIENT_CACHE_MAX_TASKDATASTORE_COUNT", CLIENT_CACHE_MAX_FLOWDATASTORE_COUNT * 100
)


###
# Datatools (S3) configuration
###
S3_ENDPOINT_URL = from_conf("S3_ENDPOINT_URL")
S3_VERIFY_CERTIFICATE = from_conf("S3_VERIFY_CERTIFICATE")

# Set ServerSideEncryption for S3 uploads
S3_SERVER_SIDE_ENCRYPTION = from_conf("S3_SERVER_SIDE_ENCRYPTION")

# S3 retry configuration
# This is useful if you want to "fail fast" on S3 operations; use with caution
# though as this may increase failures. Note that this is the number of *retries*
# so setting it to 0 means each operation will be tried once.
S3_RETRY_COUNT = from_conf("S3_RETRY_COUNT", 7)

# Number of concurrent S3 processes for parallel operations.
S3_WORKER_COUNT = from_conf("S3_WORKER_COUNT", 64)

# Number of retries on *transient* failures (such as SlowDown errors). Note
# that if after S3_TRANSIENT_RETRY_COUNT times, all operations haven't been done,
# it will try up to S3_RETRY_COUNT again so the total number of tries can be up to
# (S3_RETRY_COUNT + 1) * (S3_TRANSIENT_RETRY_COUNT + 1)
# You typically want this number fairly high as transient retires are "cheap" (only
# operations that have not succeeded retry as opposed to all operations for the
# top-level retries)
S3_TRANSIENT_RETRY_COUNT = from_conf("S3_TRANSIENT_RETRY_COUNT", 20)

# S3 retry configuration used in the aws client
# Use the adaptive retry strategy by default
S3_CLIENT_RETRY_CONFIG = from_conf(
    "S3_CLIENT_RETRY_CONFIG", {"max_attempts": 10, "mode": "adaptive"}
)

# Threshold to start printing warnings for an AWS retry
RETRY_WARNING_THRESHOLD = 3

# S3 datatools root location
DATATOOLS_SUFFIX = from_conf("DATATOOLS_SUFFIX", "data")
DATATOOLS_S3ROOT = from_conf(
    "DATATOOLS_S3ROOT",
    (
        os.path.join(DATASTORE_SYSROOT_S3, DATATOOLS_SUFFIX)
        if DATASTORE_SYSROOT_S3
        else None
    ),
)

TEMPDIR = from_conf("TEMPDIR", ".")

DATATOOLS_CLIENT_PARAMS = from_conf("DATATOOLS_CLIENT_PARAMS", {})
if S3_ENDPOINT_URL:
    DATATOOLS_CLIENT_PARAMS["endpoint_url"] = S3_ENDPOINT_URL
if S3_VERIFY_CERTIFICATE:
    DATATOOLS_CLIENT_PARAMS["verify"] = S3_VERIFY_CERTIFICATE

DATATOOLS_SESSION_VARS = from_conf("DATATOOLS_SESSION_VARS", {})

# Azure datatools root location
# Note: we do not expose an actual datatools library for Azure (like we do for S3)
# Similar to DATATOOLS_LOCALROOT, this is used ONLY by the IncludeFile's internal implementation.
DATATOOLS_AZUREROOT = from_conf(
    "DATATOOLS_AZUREROOT",
    (
        os.path.join(DATASTORE_SYSROOT_AZURE, DATATOOLS_SUFFIX)
        if DATASTORE_SYSROOT_AZURE
        else None
    ),
)
# GS datatools root location
# Note: we do not expose an actual datatools library for GS (like we do for S3)
# Similar to DATATOOLS_LOCALROOT, this is used ONLY by the IncludeFile's internal implementation.
DATATOOLS_GSROOT = from_conf(
    "DATATOOLS_GSROOT",
    (
        os.path.join(DATASTORE_SYSROOT_GS, DATATOOLS_SUFFIX)
        if DATASTORE_SYSROOT_GS
        else None
    ),
)
# Local datatools root location
DATATOOLS_LOCALROOT = from_conf(
    "DATATOOLS_LOCALROOT",
    (
        os.path.join(DATASTORE_SYSROOT_LOCAL, DATATOOLS_SUFFIX)
        if DATASTORE_SYSROOT_LOCAL
        else None
    ),
)

# Secrets Backend - AWS Secrets Manager configuration
AWS_SECRETS_MANAGER_DEFAULT_REGION = from_conf("AWS_SECRETS_MANAGER_DEFAULT_REGION")

# Secrets Backend - GCP Secrets name prefix. With this, users don't have
# to specify the full secret name in the @secret decorator.
#
# Note that it makes a difference whether the prefix ends with a slash or not
# E.g. if secret name passed to @secret decorator is mysecret:
# - "projects/1234567890/secrets/" -> "projects/1234567890/secrets/mysecret"
# - "projects/1234567890/secrets/foo-" -> "projects/1234567890/secrets/foo-mysecret"
GCP_SECRET_MANAGER_PREFIX = from_conf("GCP_SECRET_MANAGER_PREFIX")

# Secrets Backend - Azure Key Vault prefix. With this, users don't have to
# specify the full https:// vault url in the @secret decorator.
#
# It does not make a difference if the prefix ends in a / or not. We will handle either
# case correctly.
AZURE_KEY_VAULT_PREFIX = from_conf("AZURE_KEY_VAULT_PREFIX")

# The root directory to save artifact pulls in, when using S3 or Azure
ARTIFACT_LOCALROOT = from_conf("ARTIFACT_LOCALROOT", os.getcwd())

# Cards related config variables
CARD_SUFFIX = "mf.cards"
CARD_LOCALROOT = from_conf("CARD_LOCALROOT")
CARD_S3ROOT = from_conf(
    "CARD_S3ROOT",
    os.path.join(DATASTORE_SYSROOT_S3, CARD_SUFFIX) if DATASTORE_SYSROOT_S3 else None,
)
CARD_AZUREROOT = from_conf(
    "CARD_AZUREROOT",
    (
        os.path.join(DATASTORE_SYSROOT_AZURE, CARD_SUFFIX)
        if DATASTORE_SYSROOT_AZURE
        else None
    ),
)
CARD_GSROOT = from_conf(
    "CARD_GSROOT",
    os.path.join(DATASTORE_SYSROOT_GS, CARD_SUFFIX) if DATASTORE_SYSROOT_GS else None,
)
CARD_NO_WARNING = from_conf("CARD_NO_WARNING", False)

RUNTIME_CARD_RENDER_INTERVAL = from_conf("RUNTIME_CARD_RENDER_INTERVAL", 60)

# Azure storage account URL
AZURE_STORAGE_BLOB_SERVICE_ENDPOINT = from_conf("AZURE_STORAGE_BLOB_SERVICE_ENDPOINT")

# Azure storage can use process-based parallelism instead of threads.
# Processes perform better for high throughput workloads (e.g. many huge artifacts)
AZURE_STORAGE_WORKLOAD_TYPE = from_conf(
    "AZURE_STORAGE_WORKLOAD_TYPE",
    default="general",
    validate_fn=get_validate_choice_fn(["general", "high_throughput"]),
)

# GS storage can use process-based parallelism instead of threads.
# Processes perform better for high throughput workloads (e.g. many huge artifacts)
GS_STORAGE_WORKLOAD_TYPE = from_conf(
    "GS_STORAGE_WORKLOAD_TYPE",
    "general",
    validate_fn=get_validate_choice_fn(["general", "high_throughput"]),
)

###
# Metadata configuration
###
SERVICE_URL = from_conf("SERVICE_URL")
SERVICE_RETRY_COUNT = from_conf("SERVICE_RETRY_COUNT", 5)
SERVICE_AUTH_KEY = from_conf("SERVICE_AUTH_KEY")
SERVICE_HEADERS = from_conf("SERVICE_HEADERS", {})
if SERVICE_AUTH_KEY is not None:
    SERVICE_HEADERS["x-api-key"] = SERVICE_AUTH_KEY
# Checks version compatibility with Metadata service
SERVICE_VERSION_CHECK = from_conf("SERVICE_VERSION_CHECK", True)

# Default container image
DEFAULT_CONTAINER_IMAGE = from_conf("DEFAULT_CONTAINER_IMAGE")
# Default container registry
DEFAULT_CONTAINER_REGISTRY = from_conf("DEFAULT_CONTAINER_REGISTRY")
# Controls whether to include foreach stack information in metadata.
INCLUDE_FOREACH_STACK = from_conf("INCLUDE_FOREACH_STACK", True)
# Maximum length of the foreach value string to be stored in each ForeachFrame.
MAXIMUM_FOREACH_VALUE_CHARS = from_conf("MAXIMUM_FOREACH_VALUE_CHARS", 30)
# The default runtime limit (In seconds) of jobs launched by any compute provider. Default of 5 days.
DEFAULT_RUNTIME_LIMIT = from_conf("DEFAULT_RUNTIME_LIMIT", 5 * 24 * 60 * 60)

###
# Organization customizations
###
UI_URL = from_conf("UI_URL")

###
# Capture error logs from argo
###
ARGO_WORKFLOWS_CAPTURE_ERROR_SCRIPT = from_conf("ARGO_WORKFLOWS_CAPTURE_ERROR_SCRIPT")

# Contact information displayed when running the `metaflow` command.
# Value should be a dictionary where:
#  - key is a string describing contact method
#  - value is a string describing contact itself (email, web address, etc.)
# The default value shows an example of this
CONTACT_INFO = from_conf(
    "CONTACT_INFO",
    {
        "Read the documentation": "http://docs.metaflow.org",
        "Chat with us": "http://chat.metaflow.org",
        "Get help by email": "help@metaflow.org",
    },
)


###
# Decorators
###
# Format is a space separated string of decospecs (what is passed
# using --with)
DEFAULT_DECOSPECS = from_conf("DEFAULT_DECOSPECS", "")

###
# AWS Batch configuration
###
# IAM role for AWS Batch container with Amazon S3 access
# (and AWS DynamoDb access for AWS StepFunctions, if enabled)
ECS_S3_ACCESS_IAM_ROLE = from_conf("ECS_S3_ACCESS_IAM_ROLE")
# IAM role for AWS Batch container for AWS Fargate
ECS_FARGATE_EXECUTION_ROLE = from_conf("ECS_FARGATE_EXECUTION_ROLE")
# Job queue for AWS Batch
BATCH_JOB_QUEUE = from_conf("BATCH_JOB_QUEUE")
# Default container image for AWS Batch
BATCH_CONTAINER_IMAGE = from_conf("BATCH_CONTAINER_IMAGE", DEFAULT_CONTAINER_IMAGE)
# Default container registry for AWS Batch
BATCH_CONTAINER_REGISTRY = from_conf(
    "BATCH_CONTAINER_REGISTRY", DEFAULT_CONTAINER_REGISTRY
)
# Metadata service URL for AWS Batch
SERVICE_INTERNAL_URL = from_conf("SERVICE_INTERNAL_URL", SERVICE_URL)

# Assign resource tags to AWS Batch jobs. Set to False by default since
# it requires `Batch:TagResource` permissions which may not be available
# in all Metaflow deployments. Hopefully, some day we can flip the
# default to True.
BATCH_EMIT_TAGS = from_conf("BATCH_EMIT_TAGS", False)

###
# AWS Step Functions configuration
###
# IAM role for AWS Step Functions with AWS Batch and AWS DynamoDb access
# https://docs.aws.amazon.com/step-functions/latest/dg/batch-iam.html
SFN_IAM_ROLE = from_conf("SFN_IAM_ROLE")
# AWS DynamoDb Table name (with partition key - `pathspec` of type string)
SFN_DYNAMO_DB_TABLE = from_conf("SFN_DYNAMO_DB_TABLE")
# IAM role for AWS Events with AWS Step Functions access
# https://docs.aws.amazon.com/eventbridge/latest/userguide/auth-and-access-control-eventbridge.html
EVENTS_SFN_ACCESS_IAM_ROLE = from_conf("EVENTS_SFN_ACCESS_IAM_ROLE")
# Prefix for AWS Step Functions state machines. Set to stack name for Metaflow
# sandbox.
SFN_STATE_MACHINE_PREFIX = from_conf("SFN_STATE_MACHINE_PREFIX")
# Optional AWS CloudWatch Log Group ARN for emitting AWS Step Functions state
# machine execution logs. This needs to be available when using the
# `step-functions create --log-execution-history` command.
SFN_EXECUTION_LOG_GROUP_ARN = from_conf("SFN_EXECUTION_LOG_GROUP_ARN")
# Amazon S3 path for storing the results of AWS Step Functions Distributed Map
SFN_S3_DISTRIBUTED_MAP_OUTPUT_PATH = from_conf(
    "SFN_S3_DISTRIBUTED_MAP_OUTPUT_PATH",
    (
        os.path.join(DATASTORE_SYSROOT_S3, "sfn_distributed_map_output")
        if DATASTORE_SYSROOT_S3
        else None
    ),
)
###
# Kubernetes configuration
###
# Kubernetes namespace to use for all objects created by Metaflow
KUBERNETES_NAMESPACE = from_conf("KUBERNETES_NAMESPACE", "default")
# Default service account to use by K8S jobs created by Metaflow
KUBERNETES_SERVICE_ACCOUNT = from_conf("KUBERNETES_SERVICE_ACCOUNT")
# Default node selectors to use by K8S jobs created by Metaflow - foo=bar,baz=bab
KUBERNETES_NODE_SELECTOR = from_conf("KUBERNETES_NODE_SELECTOR", "")
KUBERNETES_TOLERATIONS = from_conf("KUBERNETES_TOLERATIONS", "")
KUBERNETES_PERSISTENT_VOLUME_CLAIMS = from_conf(
    "KUBERNETES_PERSISTENT_VOLUME_CLAIMS", ""
)
KUBERNETES_SECRETS = from_conf("KUBERNETES_SECRETS", "")
# Default labels for kubernetes pods
KUBERNETES_LABELS = from_conf("KUBERNETES_LABELS", "")
# Default annotations for kubernetes pods
KUBERNETES_ANNOTATIONS = from_conf("KUBERNETES_ANNOTATIONS", "")
# Default GPU vendor to use by K8S jobs created by Metaflow (supports nvidia, amd)
KUBERNETES_GPU_VENDOR = from_conf("KUBERNETES_GPU_VENDOR", "nvidia")
# Default container image for K8S
KUBERNETES_CONTAINER_IMAGE = from_conf(
    "KUBERNETES_CONTAINER_IMAGE", DEFAULT_CONTAINER_IMAGE
)
# Image pull policy for container images
KUBERNETES_IMAGE_PULL_POLICY = from_conf("KUBERNETES_IMAGE_PULL_POLICY", None)
# Image pull secrets for container images
KUBERNETES_IMAGE_PULL_SECRETS = from_conf("KUBERNETES_IMAGE_PULL_SECRETS", "")
# Default container registry for K8S
KUBERNETES_CONTAINER_REGISTRY = from_conf(
    "KUBERNETES_CONTAINER_REGISTRY", DEFAULT_CONTAINER_REGISTRY
)
# Toggle for trying to fetch EC2 instance metadata
KUBERNETES_FETCH_EC2_METADATA = from_conf("KUBERNETES_FETCH_EC2_METADATA", False)
# Shared memory in MB to use for this step
KUBERNETES_SHARED_MEMORY = from_conf("KUBERNETES_SHARED_MEMORY", None)
# Default port number to open on the pods
KUBERNETES_PORT = from_conf("KUBERNETES_PORT", None)
# Default kubernetes resource requests for CPU, memory and disk
KUBERNETES_CPU = from_conf("KUBERNETES_CPU", None)
KUBERNETES_MEMORY = from_conf("KUBERNETES_MEMORY", None)
KUBERNETES_DISK = from_conf("KUBERNETES_DISK", None)
# Default kubernetes QoS class
KUBERNETES_QOS = from_conf("KUBERNETES_QOS", "burstable")

# Architecture of kubernetes nodes - used for @conda/@pypi in metaflow-dev
KUBERNETES_CONDA_ARCH = from_conf("KUBERNETES_CONDA_ARCH")
ARGO_WORKFLOWS_KUBERNETES_SECRETS = from_conf("ARGO_WORKFLOWS_KUBERNETES_SECRETS", "")
ARGO_WORKFLOWS_ENV_VARS_TO_SKIP = from_conf("ARGO_WORKFLOWS_ENV_VARS_TO_SKIP", "")

KUBERNETES_JOBSET_GROUP = from_conf("KUBERNETES_JOBSET_GROUP", "jobset.x-k8s.io")
KUBERNETES_JOBSET_VERSION = from_conf("KUBERNETES_JOBSET_VERSION", "v1alpha2")

##
# Argo Events Configuration
##
ARGO_EVENTS_SERVICE_ACCOUNT = from_conf("ARGO_EVENTS_SERVICE_ACCOUNT")
ARGO_EVENTS_EVENT_BUS = from_conf("ARGO_EVENTS_EVENT_BUS", "default")
ARGO_EVENTS_EVENT_SOURCE = from_conf("ARGO_EVENTS_EVENT_SOURCE")
ARGO_EVENTS_EVENT = from_conf("ARGO_EVENTS_EVENT")
ARGO_EVENTS_WEBHOOK_URL = from_conf("ARGO_EVENTS_WEBHOOK_URL")
ARGO_EVENTS_INTERNAL_WEBHOOK_URL = from_conf(
    "ARGO_EVENTS_INTERNAL_WEBHOOK_URL", ARGO_EVENTS_WEBHOOK_URL
)
ARGO_EVENTS_WEBHOOK_AUTH = from_conf("ARGO_EVENTS_WEBHOOK_AUTH", "none")

ARGO_WORKFLOWS_UI_URL = from_conf("ARGO_WORKFLOWS_UI_URL")

##
# Airflow Configuration
##
# This configuration sets `startup_timeout_seconds` in airflow's KubernetesPodOperator.
AIRFLOW_KUBERNETES_STARTUP_TIMEOUT_SECONDS = from_conf(
    "AIRFLOW_KUBERNETES_STARTUP_TIMEOUT_SECONDS", 60 * 60
)
# This configuration sets `kubernetes_conn_id` in airflow's KubernetesPodOperator.
AIRFLOW_KUBERNETES_CONN_ID = from_conf("AIRFLOW_KUBERNETES_CONN_ID")
AIRFLOW_KUBERNETES_KUBECONFIG_FILE = from_conf("AIRFLOW_KUBERNETES_KUBECONFIG_FILE")
AIRFLOW_KUBERNETES_KUBECONFIG_CONTEXT = from_conf(
    "AIRFLOW_KUBERNETES_KUBECONFIG_CONTEXT"
)


###
# Conda configuration
###
# Conda package root location on S3
CONDA_PACKAGE_S3ROOT = from_conf("CONDA_PACKAGE_S3ROOT")
# Conda package root location on Azure
CONDA_PACKAGE_AZUREROOT = from_conf("CONDA_PACKAGE_AZUREROOT")
# Conda package root location on GS
CONDA_PACKAGE_GSROOT = from_conf("CONDA_PACKAGE_GSROOT")

# Use an alternate dependency resolver for conda packages instead of conda
# Mamba promises faster package dependency resolution times, which
# should result in an appreciable speedup in flow environment initialization.
CONDA_DEPENDENCY_RESOLVER = from_conf("CONDA_DEPENDENCY_RESOLVER", "conda")

# Default to not using fast init binary.
CONDA_USE_FAST_INIT = from_conf("CONDA_USE_FAST_INIT", False)

###
# Escape hatch configuration
###
# Print out warning if escape hatch is not used for the target packages
ESCAPE_HATCH_WARNING = from_conf("ESCAPE_HATCH_WARNING", True)

###
# Features
###
FEAT_ALWAYS_UPLOAD_CODE_PACKAGE = from_conf("FEAT_ALWAYS_UPLOAD_CODE_PACKAGE", False)
###
# Debug configuration
###
DEBUG_OPTIONS = [
    "subcommand",
    "sidecar",
    "s3client",
    "tracing",
    "stubgen",
    "userconf",
    "conda",
    "package",
]

for typ in DEBUG_OPTIONS:
    vars()["DEBUG_%s" % typ.upper()] = from_conf("DEBUG_%s" % typ.upper(), False)

###
# Plugin configuration
###

# Plugin configuration variables exist in plugins/__init__.py.
# Specifically, there is an ENABLED_<category> configuration value to determine
# the set of plugins to enable. The categories are: step_decorator, flow_decorator,
# environment, metadata_provider, datastore, sidecar, logging_sidecar, monitor_sidecar,
# aws_client_provider, and cli. If not set (the default), all plugins are enabled.
# You can restrict which plugins are enabled by listing them explicitly, for example
# ENABLED_STEP_DECORATOR = ["batch", "resources"] will enable only those two step
# decorators and none other.

###
# Command configuration
###

# Command (ie: metaflow <cmd>) configuration variable ENABLED_CMD
# exists in cmd/main_cli.py. It behaves just like any of the other ENABLED_<category>
# configuration variables.

###
# AWS Sandbox configuration
###
# Boolean flag for metaflow AWS sandbox access
AWS_SANDBOX_ENABLED = from_conf("AWS_SANDBOX_ENABLED", False)
# Metaflow AWS sandbox auth endpoint
AWS_SANDBOX_STS_ENDPOINT_URL = SERVICE_URL
# Metaflow AWS sandbox API auth key
AWS_SANDBOX_API_KEY = from_conf("AWS_SANDBOX_API_KEY")
# Internal Metadata URL
AWS_SANDBOX_INTERNAL_SERVICE_URL = from_conf("AWS_SANDBOX_INTERNAL_SERVICE_URL")
# AWS region
AWS_SANDBOX_REGION = from_conf("AWS_SANDBOX_REGION")


# Finalize configuration
if AWS_SANDBOX_ENABLED:
    os.environ["AWS_DEFAULT_REGION"] = AWS_SANDBOX_REGION
    SERVICE_INTERNAL_URL = AWS_SANDBOX_INTERNAL_SERVICE_URL
    SERVICE_HEADERS["x-api-key"] = AWS_SANDBOX_API_KEY
    SFN_STATE_MACHINE_PREFIX = from_conf("AWS_SANDBOX_STACK_NAME")

KUBERNETES_SANDBOX_INIT_SCRIPT = from_conf("KUBERNETES_SANDBOX_INIT_SCRIPT")

OTEL_ENDPOINT = from_conf("OTEL_ENDPOINT")
ZIPKIN_ENDPOINT = from_conf("ZIPKIN_ENDPOINT")
CONSOLE_TRACE_ENABLED = from_conf("CONSOLE_TRACE_ENABLED", False)
# internal env used for preventing the tracing module from loading during Conda bootstrapping.
DISABLE_TRACING = bool(os.environ.get("DISABLE_TRACING", False))

# MAX_ATTEMPTS is the maximum number of attempts, including the first
# task, retries, and the final fallback task and its retries.
#
# Datastore needs to check all attempt files to find the latest one, so
# increasing this limit has real performance implications for all tasks.
# Decreasing this limit is very unsafe, as it can lead to wrong results
# being read from old tasks.
#
# Note also that DataStoreSet resolves the latest attempt_id using
# lexicographic ordering of attempts. This won't work if MAX_ATTEMPTS > 99.
MAX_ATTEMPTS = 6

# Feature flag (experimental features that are *explicitly* unsupported)

# Process configs even when using the click_api for Runner/Deployer
CLICK_API_PROCESS_CONFIG = from_conf("CLICK_API_PROCESS_CONFIG", False)


# PINNED_CONDA_LIBS are the libraries that metaflow depends on for execution
# and are needed within a conda environment
def get_pinned_conda_libs(python_version, datastore_type):
    pins = {
        "requests": ">=2.21.0",
    }
    if datastore_type == "s3":
        pins["boto3"] = ">=1.14.0"
    elif datastore_type == "azure":
        pins["azure-identity"] = ">=1.10.0"
        pins["azure-storage-blob"] = ">=12.12.0"
        pins["azure-keyvault-secrets"] = ">=4.7.0"
        pins["simple-azure-blob-downloader"] = ">=0.1.0"
    elif datastore_type == "gs":
        pins["google-cloud-storage"] = ">=2.5.0"
        pins["google-auth"] = ">=2.11.0"
        pins["google-cloud-secret-manager"] = ">=2.10.0"
        pins["simple-gcp-object-downloader"] = ">=0.1.0"
    elif datastore_type == "local":
        pass
    else:
        raise MetaflowException(
            msg="conda lib pins for datastore %s are undefined" % (datastore_type,)
        )
    return pins


# Check if there are extensions to Metaflow to load and override everything
try:
    from metaflow.extension_support import get_modules

    _TOGGLE_DECOSPECS = []

    ext_modules = get_modules("config")
    for m in ext_modules:
        # We load into globals whatever we have in extension_module
        # We specifically exclude any modules that may be included (like sys, os, etc)
        for n, o in m.module.__dict__.items():
            if n == "DEBUG_OPTIONS":
                DEBUG_OPTIONS.extend(o)
                for typ in o:
                    vars()["DEBUG_%s" % typ.upper()] = from_conf(
                        "DEBUG_%s" % typ.upper(), False
                    )
            elif n == "get_pinned_conda_libs":

                def _new_get_pinned_conda_libs(
                    python_version, datastore_type, f1=globals()[n], f2=o
                ):
                    d1 = f1(python_version, datastore_type)
                    d2 = f2(python_version, datastore_type)
                    for k, v in d2.items():
                        d1[k] = v if k not in d1 else ",".join([d1[k], v])
                    return d1

                globals()[n] = _new_get_pinned_conda_libs
            elif n == "TOGGLE_DECOSPECS":
                if any([x.startswith("-") for x in o]):
                    raise ValueError("Removing decospecs is not currently supported")
                if any(" " in x for x in o):
                    raise ValueError("Decospecs cannot contain spaces")
                _TOGGLE_DECOSPECS.extend(o)
            elif not n.startswith("__") and not isinstance(o, types.ModuleType):
                globals()[n] = o
    # If DEFAULT_DECOSPECS is set, use that, else extrapolate from extensions
    if not DEFAULT_DECOSPECS:
        DEFAULT_DECOSPECS = " ".join(_TOGGLE_DECOSPECS)

finally:
    # Erase all temporary names to avoid leaking things
    for _n in [
        "m",
        "n",
        "o",
        "typ",
        "ext_modules",
        "get_modules",
        "_new_get_pinned_conda_libs",
        "d1",
        "d2",
        "k",
        "v",
        "f1",
        "f2",
        "_TOGGLE_DECOSPECS",
    ]:
        try:
            del globals()[_n]
        except KeyError:
            pass
    del globals()["_n"]

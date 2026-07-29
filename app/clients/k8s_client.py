from kubernetes import client, config


class K8sClient:
    def __init__(self):
        self._configured = False
        self._core_v1_cache = None
        self._networking_v1_cache = None
        self._rbac_v1_cache = None

    def _ensure_configured(self):
        # Lazy: config loading (and the API client objects built on top of
        # it) only happens on first real use, not when K8sClient() is
        # constructed. This matters because a module-level singleton
        # (k8s_client = K8sClient(), at the bottom of this file) is created
        # as soon as this module is imported - if __init__ loaded config
        # directly, simply importing this file (e.g. from a test, or from
        # any code that imports app.routers.services) would require a
        # reachable cluster or a valid ~/.kube/config to succeed.
        if self._configured:
            return
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self._configured = True

    @property
    def _core_v1(self):
        self._ensure_configured()
        if self._core_v1_cache is None:
            self._core_v1_cache = client.CoreV1Api()
        return self._core_v1_cache

    @property
    def _networking_v1(self):
        self._ensure_configured()
        if self._networking_v1_cache is None:
            self._networking_v1_cache = client.NetworkingV1Api()
        return self._networking_v1_cache

    @property
    def _rbac_v1(self):
        self._ensure_configured()
        if self._rbac_v1_cache is None:
            self._rbac_v1_cache = client.RbacAuthorizationV1Api()
        return self._rbac_v1_cache

    def namespace_exists(self, namespace: str) -> bool:
        try:
            self._core_v1.read_namespace(name=namespace)
            return True
        except client.ApiException as e:
            if e.status == 404:
                return False
            raise

    def create_namespace(self, namespace: str, labels: dict = None):
        if self.namespace_exists(namespace):
            return

        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels=labels or {},
            )
        )
        self._core_v1.create_namespace(body=body)

    def ensure_resource_quota(self, namespace: str):
        quota_name = "default-quota"
        try:
            self._core_v1.read_namespaced_resource_quota(name=quota_name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(name=quota_name),
            spec=client.V1ResourceQuotaSpec(
                hard={
                    "requests.cpu": "4",
                    "requests.memory": "8Gi",
                    "limits.cpu": "8",
                    "limits.memory": "16Gi",
                    "pods": "20",
                }
            ),
        )
        self._core_v1.create_namespaced_resource_quota(namespace=namespace, body=body)

    def ensure_limit_range(self, namespace: str):
        limit_name = "default-limits"
        try:
            self._core_v1.read_namespaced_limit_range(name=limit_name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name=limit_name),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "250m", "memory": "256Mi"},
                        default_request={"cpu": "100m", "memory": "128Mi"},
                        max={"cpu": "1", "memory": "1Gi"},
                        min={"cpu": "50m", "memory": "64Mi"},
                    )
                ]
            ),
        )
        self._core_v1.create_namespaced_limit_range(namespace=namespace, body=body)

    def ensure_network_policy(self, namespace: str):
        policy_name = "default-allow-same-namespace-and-ingress"
        try:
            self._networking_v1.read_namespaced_network_policy(name=policy_name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name=policy_name),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(),
                policy_types=["Ingress"],
                ingress=[
                    client.V1NetworkPolicyIngressRule(
                        _from=[
                            client.V1NetworkPolicyPeer(
                                pod_selector=client.V1LabelSelector()
                            ),
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={"kubernetes.io/metadata.name": "ingress-nginx"}
                                )
                            ),
                        ]
                    )
                ],
            ),
        )
        self._networking_v1.create_namespaced_network_policy(namespace=namespace, body=body)

    def ensure_service_account(self, namespace: str, name: str = "platform-app"):
        try:
            self._core_v1.read_namespaced_service_account(name=name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1ServiceAccount(
            metadata=client.V1ObjectMeta(name=name)
        )
        self._core_v1.create_namespaced_service_account(namespace=namespace, body=body)

    def ensure_role(self, namespace: str, name: str = "platform-app-role"):
        try:
            self._rbac_v1.read_namespaced_role(name=name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1Role(
            metadata=client.V1ObjectMeta(name=name),
            rules=[
                client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods", "services", "configmaps"],
                    verbs=["get", "list", "watch"],
                ),
            ],
        )
        self._rbac_v1.create_namespaced_role(namespace=namespace, body=body)

    def ensure_role_binding(self, namespace: str, service_account: str = "platform-app", role: str = "platform-app-role"):
        binding_name = f"{service_account}-binding"
        try:
            self._rbac_v1.read_namespaced_role_binding(name=binding_name, namespace=namespace)
            return
        except client.ApiException as e:
            if e.status != 404:
                raise

        body = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name=binding_name),
            subjects=[
                client.RbacV1Subject(
                    kind="ServiceAccount",
                    name=service_account,
                    namespace=namespace,
                )
            ],
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="Role",
                name=role,
            ),
        )
        self._rbac_v1.create_namespaced_role_binding(namespace=namespace, body=body)


k8s_client = K8sClient()


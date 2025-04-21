apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  labels:
    framework: golang
    type: HTTP
  name: pay-me.rules
  namespace: payment
spec:
  groups:
  - name: pay-me.http-service.rules
    rules:
    - alert: DesiredVsActualPods
      annotations:
        description: Desired pods for pay-me is larger than actual pods for
          too long. Please ensure everything is configured correctly.
        summary: Desired pods larger than actual pods - pay-me
      expr: |
        ((
          avg(avg_over_time(kube_horizontalpodautoscaler_status_desired_replicas{exported_namespace=~"payment"}[5m])) by (exported_namespace) /
          avg(avg_over_time(kube_deployment_spec_replicas{exported_namespace=~"payment"}[5m])) by (exported_namespace)
        ) or (
          avg(avg_over_time(kube_horizontalpodautoscaler_status_desired_replicas{namespace=~"payment"}[5m])) by (namespace) /
          avg(avg_over_time(kube_deployment_spec_replicas{namespace=~"payment"}[5m])) by (namespace)
        )) < 0.9
      for: 10m
      labels:
        owner: payments
        severity: warning
        service: pay-me
    - alert: HighMemoryConsumption
      annotations:
        description: 'Memory usage {{ $value | humanizePercentage }} of {{ $labels.namespace
          }} for container {{ $labels.container }} is too high.

          Please check the service for memory leaks or increase the memory if needed.

          '
        summary: 'High memory usage - service {{ $labels.namespace }} / container
          {{ $labels.container }}

          '
      expr: |
        (
          max(max_over_time(container_memory_usage_bytes{namespace="payment", container!=""}[5m])) by (namespace, container) /
          avg(avg_over_time(container_spec_memory_limit_bytes{namespace="payment", container!=""}[5m])) by (namespace, container)
        ) > 0.9
      for: 10m
      labels:
        owner: payments
        severity: warning
        service: pay-me
    - alert: WebServiceHighLatency
      annotations:
        dashboard_url: https://grafana.example.com/d/web-service-dashboard
        description: 95th percentile of request duration is above 2 seconds for more
          than 5 minutes.
        summary: High latency in web service
      expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="pay-me"}[5m]))
        by (le, service)) > 2
      for: 5m
      labels:
        severity: warning
        owner: payments
        service: pay-me
    - alert: WebServiceHighErrorRate
      annotations:
        dashboard_url: https://grafana.example.com/d/web-service-dashboard
        description: Error rate is above 5% for more than 3 minutes.
        summary: High error rate in web service
      expr: sum(rate(http_requests_total{service="pay-me", status_code=~"5.."}[5m]))
        / sum(rate(http_requests_total{service="pay-me"}[5m])) > 0.05
      for: 3m
      labels:
        severity: critical
        owner: payments
        service: pay-me
    - alert: WebServiceHighCPUUsage
      annotations:
        dashboard_url: https://grafana.example.com/d/web-service-dashboard
        description: CPU usage is above 85% of the limit for more than 10 minutes.
        summary: High CPU usage in web service
      expr: sum(rate(container_cpu_usage_seconds_total{namespace="payment", pod=~"pay-me-.*"}[5m]))
        / sum(kube_pod_
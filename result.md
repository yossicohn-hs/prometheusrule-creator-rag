```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  labels:
    description: Job Applications Processing Service Monitoring
    framework: python
    type: http
  name: jobme-monitoring-rules
  namespace: jobme
spec:
  groups:
  - name: alb.rules
    rules:
    - alert: ALB5xxErrorsHighCriticalPercentage
      annotations:
        description: The number of 5xx errors from the ALB target group is high > 2%.
        summary: ALB 5xx Errors Percentage High
      expr: 'increase(aws_applicationelb_httpcode_target_5_xx_count_sum{dimension_TargetGroup=~".*jobme.*", dimension_LoadBalancer=~".*prodpub.*", dimension_AvailabilityZone=""}[1m])/4/increase(aws_applicationelb_request_count_per_target_sum{dimension_TargetGroup=~".*jobme.*", dimension_LoadBalancer=~".*prodpub.*", dimension_AvailabilityZone=""}[1m]) *100 > 2'
      for: 5m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: ALBTargetResponseTimeHigh
      annotations:
        description: The average response time of the ALB target group is high.
        summary: ALB Target Response Time High
      expr: 'aws_applicationelb_target_response_time_average{dimension_TargetGroup=~".*jobme.*"} > 0.5'
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
    - alert: ALBTargetResponseTimeHighCritical
      annotations:
        description: The average response time of the ALB target group is high.
        summary: ALB Target Response Time High
      expr: 'aws_applicationelb_target_response_time_average{dimension_TargetGroup=~".*jobme.*"} > 2'
      for: 5m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: ALBUnhealthyHostsHigh
      annotations:
        description: The number of unhealthy hosts in the ALB target group is high > 1.
        summary: ALB Unhealthy Hosts High
      expr: 'max by(dimension_LoadBalancer)(aws_applicationelb_un_healthy_host_count_sum{dimension_TargetGroup=~".*jobme.*"}) > 1'
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
    - alert: ALBUnhealthyHostsHighCritical
      annotations:
        description: The number of unhealthy hosts in the ALB target group is high > 2.
        summary: ALB Unhealthy Hosts High
      expr: 'max by(dimension_LoadBalancer)(aws_applicationelb_un_healthy_host_count_sum{dimension_TargetGroup=~".*jobme.*"}) > 2'
      for: 5m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: HighRequestCount
      annotations:
        description: High count of requests for HTTP-service
        summary: High count of requests for HTTP-service
      expr: 'aws_applicationelb_request_count_average{dimension_TargetGroup=~".*jobme.*"} > 50'
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
    - alert: HighRequestCountCritical
      annotations:
        description: High count of requests for HTTP-service
        summary: High count of requests for HTTP-service
      expr: 'aws_applicationelb_request_count_average{dimension_TargetGroup=~".*jobme.*"} > 150'
      for: 5m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: LB4xxErrorsHighCriticalPercentage
      annotations:
        description: The number of 4xx errors from the ALB target group is high > 10%.
        summary: ALB 4xx Errors Percentage High
      expr: 'increase(aws_applicationelb_httpcode_target_4_xx_count_sum{dimension_TargetGroup=~".*jobme.*", dimension_LoadBalancer=~".*prodpub.*", dimension_AvailabilityZone=""}[1m])/4/increase(aws_applicationelb_request_count_per_target_sum{dimension_TargetGroup=~".*jobme.*", dimension_LoadBalancer=~".*prodpub.*", dimension_AvailabilityZone=""}[1m]) *100 > 10'
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
    - alert: HTTPLatencyCritical
      annotations:
        description: HTTP Service Latency is greater than 2 seconds
        summary: HTTP Service Latency is greater than 2 seconds
      expr: 'max by(dimension_LoadBalancer)(aws_applicationelb_target_response_time_average{dimension_TargetGroup=~".*jobme.*"}) > 2'
      for: 5m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: HTTPLatencyWarning
      annotations:
        description: HTTP Service Latency is greater than 0.5 seconds
        summary: HTTP Service Latency is greater than 0.5 seconds
      expr: 'max by(dimension_LoadBalancer)(aws_applicationelb_target_response_time_average{dimension_TargetGroup=~".*jobme.*"}) > 0.5'
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
  - name: python-http-service.alerts
    rules:
    - alert: PythonWebServiceHighLatency
      annotations:
        dashboard_url: https://grafana.example.com/d/web-service-dashboard
        description: 95th percentile of request duration is above 2 seconds for more than 5 minutes.
        summary: High latency in web service
      expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="jobme", namespace="jobme"}[5m])) by (le, service)) > 2
      for: 5m
      labels:
        owner: core
        severity: warning
        service: jobme
    - alert: PythonWebServiceHighErrorRate
      annotations:
        dashboard_url: https://grafana.example.com/d/web-service-dashboard
        description: Error rate is above 5% for more than 3 minutes.
        summary: High error rate in web service
      expr: sum(rate(http_requests_total{service="jobme", namespace="jobme", status_code=~"5.."}[5m])) / sum(rate(http_requests_total{service="jobme", namespace="jobme"}[5m])) > 0.05
      for: 3m
      labels:
        owner: core
        severity: critical
        service: jobme
  - name: opensearch.rules
    rules:
    - alert: ClusterHighCPU
      annotations:
        description: OpenSearch cluster {{ $labels.dimension_DomainName }} - CPU Utilization is more than {{ $value | humanizePercentage }} for 15 minutes
        summary: 'OpenSearch {{ $labels.dimension_DomainName }} has high cpu {{ $value | humanizePercentage }}'
      expr: 'avg(aws_es_master_cpuutilization_average) > 90'
      for: 15m
      labels:
        owner: core
        severity: critical
        service: jobme
    - alert: ClusterStatusRed
      annotations:
        description: ElasticOpenSearch cluster {{ $labels.
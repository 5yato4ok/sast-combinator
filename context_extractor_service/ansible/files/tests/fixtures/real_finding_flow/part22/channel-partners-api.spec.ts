const orgId = 'org';
const serviceId = 'service';
const periodStartDate = '2024-01-01';

service.reports.organizations
    .getExpiringServiceDetailDialog(orgId, serviceId, periodStartDate)
    .subscribe();

class ServerCertificateWarning: public QnMessageBox
{
public:
    explicit ServerCertificateWarning(
        const QList<core::TargetCertificateInfo>& certificatesInfo);
};

ServerCertificateWarning::ServerCertificateWarning(
    const QList<core::TargetCertificateInfo>& certificatesInfo)
{
    auto certificateDetailsLabel = new QLabel(
        common::html::localLink(tr("Certificate details"), kCertificateLink));
    connect(certificateDetailsLabel , &QLabel::linkActivated, this,
        [this, statistics, certificateInfo, statisticsName](const QString& link)
        {
            if (link == kCertificateLink)
            {
                auto viewer = new ServerCertificateViewer(
                    certificateInfo,
                    ServerCertificateViewer::Mode::presented,
                    this);
            }
        });
}

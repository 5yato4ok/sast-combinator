class ServerCertificateWarning: public QnMessageBox
{
public:
    explicit ServerCertificateWarning(
        const QList<core::TargetCertificateInfo>& certificatesInfo);
};

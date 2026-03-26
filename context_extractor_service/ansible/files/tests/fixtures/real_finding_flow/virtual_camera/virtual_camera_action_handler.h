namespace nx::vms::client::desktop {

class VirtualCameraActionHandler:
    public QObject,
    public WindowContextAware
{
    using base_type = QObject;

public:
    explicit VirtualCameraActionHandler(WindowContext* windowContext, QObject* parent = nullptr);
    virtual ~VirtualCameraActionHandler() override;
};

} // namespace nx::vms::client::desktop

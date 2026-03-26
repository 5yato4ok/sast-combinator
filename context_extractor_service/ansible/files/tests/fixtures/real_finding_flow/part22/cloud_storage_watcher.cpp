class CloudStorageWatcher
{
};

CloudStorageWatcher::CloudStorageWatcher()
{
    auto storageChangesListener = new core::SessionResourcesSignalListener<QnStorageResource>(
        systemContext(),
        this);
}

CloudStorageWatcher::~CloudStorageWatcher() = default;

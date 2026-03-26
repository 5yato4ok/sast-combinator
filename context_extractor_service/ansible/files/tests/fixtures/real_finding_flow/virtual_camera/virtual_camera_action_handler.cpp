#include "virtual_camera_action_handler.h"
#include <nx/vms/client/desktop/menu/action.h>

namespace nx::vms::client::desktop {

VirtualCameraActionHandler::VirtualCameraActionHandler(
    WindowContext* windowContext,
    QObject* parent)
    :
    base_type(parent),
    WindowContextAware(windowContext)
{
    using namespace menu;

    new QnVirtualCameraSessionDelegate(this);
}

VirtualCameraActionHandler::~VirtualCameraActionHandler()
{
}

} // namespace nx::vms::client::desktop

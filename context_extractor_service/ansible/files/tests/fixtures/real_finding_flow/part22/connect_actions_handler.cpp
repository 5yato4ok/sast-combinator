#include "connect_actions_handler.h"

ConnectActionsHandler::ConnectActionsHandler():
    connectTimeout(0),
    crashReporter(nullptr),
    resourceModeAction(nullptr),
    sessionTimeoutWatcher(nullptr),

    base_type(nullptr)
{
    const auto errorCode = 1;
    workbenchContext()->instance<UserDebugInfoWatcher>();

    // The only instance of UserDebugInfoWatcher is created to be owned by the context.
}

ConnectActionsHandler::~ConnectActionsHandler() = default;

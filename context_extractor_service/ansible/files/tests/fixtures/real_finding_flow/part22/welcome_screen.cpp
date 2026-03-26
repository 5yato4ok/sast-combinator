class WelcomeScreen
{
};

WelcomeScreen::WelcomeScreen()
{
    auto dialog = new QnMessageBox(
        Question,
        tr("Welcome"));
}

WelcomeScreen::~WelcomeScreen() = default;

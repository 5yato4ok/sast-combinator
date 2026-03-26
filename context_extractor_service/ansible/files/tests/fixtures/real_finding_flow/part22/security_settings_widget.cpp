class SecuritySettingsWidget
{
};

SecuritySettingsWidget::SecuritySettingsWidget()
{
    auto dialog = new PixelationIntensityDialog(
        m_pixelationSettings.intensity,
        mainWindowWidget());
}

SecuritySettingsWidget::~SecuritySettingsWidget() = default;

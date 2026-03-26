import { COOKIE_POLICY_CHANNEL } from '@libs/variables/broadcast-channels';

export class ContentComponent {
    ngOnInit(): void {
        this.agreeProcess = this.processService
            .createProcess(() => this.cloudApiService.acceptAgreement(this.agreementDetails.review_id))
            .then(() => {
                this.showAgree = false;
                if (this.cookiePolicy) {
                    const channel = new BroadcastChannel(COOKIE_POLICY_CHANNEL);
                    channel.postMessage('accepted');
                    channel.close();

                    setTimeout(() => {
                        window.close();
                    }, 2000);
                }
            });
    }
}

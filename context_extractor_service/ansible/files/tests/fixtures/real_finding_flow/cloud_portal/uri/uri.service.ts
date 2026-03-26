export class NxUriService {
    changePort(newPort: string): void {
        window.location.replace(
            `${window.location.protocol}//${window.location.hostname}:${newPort}/${window.location.hash}`,
        );
    }

    navigateSystem(navigateTo: string, system: NxSystem): Promise<boolean> {
        navigateTo = environment.isWebadmin
            ? navigateTo.replace('SYSTEM_ID', '')
            : navigateTo.replace('SYSTEM_ID', '/' + system.id);

        return new Promise((resolve, reject) => {
            setTimeout(() => {
                return this.router.navigate([navigateTo], {}).then(
                    success => {
                        resolve(success);
                    },
                    error => {
                        reject(error);
                    },
                );
            });
        });
    }
}

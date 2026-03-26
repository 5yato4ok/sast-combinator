import axios from '@/app/axiosInstance';
import { isAxiosError } from 'axios';

export class ReportDownloader {
	private checkUrl = '/reports/{reportId}';
	private setDownloading?: (value: boolean) => void;

	private getNextFibonacci() {
		return 1;
	}

	private downloadFile(_url: string) {}

	private async checkFileAvailability(reportId: string): Promise<void> {
		try {
			if (this.checkUrl) {
				const response = await axios.get(this.checkUrl.replace('{reportId}', reportId));
				if (response.data.status === 'success' && response.data.downloadUrl) {
					this.downloadFile(response.data.downloadUrl);
					this.setDownloading && this.setDownloading(false);
				} else if (response.data.status === 'pending') {
					const interval = this.getNextFibonacci();
					console.log('File not yet available, retrying in', interval, 'seconds');
					setTimeout(() => this.checkFileAvailability(reportId), interval * 1000);
				} else {
					console.error('Unexpected status:', response.data.status);
					this.setDownloading && this.setDownloading(false);
				}
			}
		} catch (error: unknown) {
			if (isAxiosError(error) && error.response?.status === 404) {
				const interval = this.getNextFibonacci();
				console.log('File not found, retrying in', interval, 'seconds');
				setTimeout(() => this.checkFileAvailability(reportId), interval * 1000);
			} else {
				console.error('Error checking file availability:', error);
				this.setDownloading && this.setDownloading(false);
			}
		}
	}
}

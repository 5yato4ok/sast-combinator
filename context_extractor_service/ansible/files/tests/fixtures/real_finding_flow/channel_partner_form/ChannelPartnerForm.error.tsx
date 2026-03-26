import axios from '@/app/axiosInstance';

export default function ChannelPartnerForm() {
	const createChannelPartner = async () => {
		try {
			await axios.post('channel_partners/', {});
		} catch (error) {
			console.error('Error during channel partner creation: ', error);
		}
	};

	return createChannelPartner;
}

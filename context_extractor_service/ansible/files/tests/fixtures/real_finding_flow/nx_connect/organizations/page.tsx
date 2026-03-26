import axios from '@/app/axiosInstance';

type ServicesAvailable = unknown[];

export default async function OrganizationDetails() {
	const pd = { revenuePastYear: { jan: { id: 0 } } };
	const rootChannelPartner = { id: 'cp-1' };
	const quantity = 2;
	const price = 3;
	const service = { numberAddedForEachService: 0 };
	Object.keys(pd.revenuePastYear).forEach((month: string) => {
		console.log(month);
	});
	const availableServices = (
		await axios.get(`channel_partners/${rootChannelPartner?.id}/services/available/`)
	).data as ServicesAvailable;
	pd.revenuePastYear.jan.id += quantity * price;
	service.numberAddedForEachService += quantity;
	return { availableServices, service };
}

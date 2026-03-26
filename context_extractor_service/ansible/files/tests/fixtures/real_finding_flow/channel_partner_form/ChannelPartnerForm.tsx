import axios from '@/app/axiosInstance';
import { useContext, useState } from 'react';

export default function ChannelPartnerForm(props: ChannelPartnerFormProps) {
	const ctx = useContext(NxUserContext);
	const rootChannelPartner = ctx?.user?.channelPartner;
	const queryClient = useQueryClient();
	const { toggleCreateChannelPartnerWithServices } = useCustomizationToggles();

	const [isCreatingChannelPartner, setIsCreatingChannelPartner] = useState(false);

	const getRoles = async () => {
		const rolesResponse = await axios.get(`/channel_partner_roles`);
		return rolesResponse.data;
	};

	const { data: rolesData } = useQuery('roles', getRoles);
	const { data: usersData } = useChannelPartnerUsers(rootChannelPartner?.id);

	const changeStage = (stage: number) => {
		if (props.onChangeStage) {
			props.onChangeStage(stage ?? 0);
		}
	};

	const deleteUser = (email: string, newSubCpId: string) => {
		return axios
			.delete(`/channel_partners/${newSubCpId}/users/${email}`)
			.then()
			.catch((error) => {
				console.error(`Error deleting user ${email}`, error);
			});
	};
}

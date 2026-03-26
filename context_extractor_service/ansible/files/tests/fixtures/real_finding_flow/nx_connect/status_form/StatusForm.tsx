import { useEditEntityFormRef } from '@/app/(dashboard)/components/EntityInformation/hooks/useEditEntityFormRef';

export const StatusForm = ({ ref }: { ref: unknown }) => {
	const individualCpOrOrg = {};
	const selectedEntityState = 'active';
	const hasUnsavedChanges = () => true;
	const saveAndExit = false;
	const handleSaveButtonClick = async (_saveAndExit: boolean) => {};
	const { isSaving } = useEditEntityFormRef(
		{
			ref,
			hasUnsavedChanges,
			retry: async () => {
				await handleSaveButtonClick(saveAndExit);
			},
		},
		[individualCpOrOrg, selectedEntityState]
	);
	return isSaving;
};

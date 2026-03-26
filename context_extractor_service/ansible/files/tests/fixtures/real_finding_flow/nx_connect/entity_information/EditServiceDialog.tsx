import React from 'react';

export function EditServiceDialog() {
  const handleOpenChange = (_open: boolean) => {};
  const setVisibleSuccessToast = (_value: boolean) => {};
  const queryClient = { refetchQueries: async (_key: string) => {} };
  const patchService = async (_price: string | null) => {};
  const removeService = async () => {};
  const watch = (_name: string) => '10';
  const serviceSubType = 'paid';
  const SERVICE_SUBTYPE_DEMO = 'demo';
  const isAddedDemo = false;

  const { mutate: updateService } = useMutation({
    mutationFn: async () => {
      const price = watch('price');
      const servicePrice = serviceSubType === SERVICE_SUBTYPE_DEMO && isAddedDemo ? null : price?.toFixed(2) ?? null;
      await patchService(servicePrice);
    },
    onSuccess: async () => {
      handleOpenChange(false);
      setVisibleSuccessToast(true);
      await queryClient.refetchQueries('subChannelPartnerServices');
    },
    onError: (error: AxiosError) => {
      console.error('Error updating service:', error);
    },
  });

  const { mutate: discontinueService } = useMutation({
    mutationFn: removeService,
    onSuccess: async () => {
      handleOpenChange(false);
      setVisibleSuccessToast(true);
      await queryClient.refetchQueries('subChannelPartnerServices');
    },
    onError: (error: AxiosError) => {
      console.error('Error removing service:', error);
    },
  });

  return <button onClick={() => { updateService(); discontinueService(); }}>Save</button>;
}

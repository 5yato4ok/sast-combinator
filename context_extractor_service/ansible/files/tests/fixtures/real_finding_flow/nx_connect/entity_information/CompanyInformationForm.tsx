import React from 'react';

export function CompanyInformationForm() {
  const unexpectedErrors: unknown[] = [];
  let refetchEntity = false;
  const updateEntityInformation = async (_editType: string, _id: string, _changedData: unknown) => {};
  const getEditTypeFromCacheKey = (_key: string) => 'edit';
  const safeTrim = (value: string) => value.trim();
  const hasUnsavedAddressChanges = (_formAddress: unknown, _originalAddress: unknown) => true;
  const pruneEmptyStrings = (value: unknown) => value;
  const queryClient = { refetchQueries: async (_key: string) => {} };
  const isCpForm = (_key: string) => true;
  const formData = { name: 'Acme', website: 'example.test', address: { city: 'NY' } };
  const individualCpOrOrg = { name: 'Old', attributes: { website: 'old.test', address: {} } };
  const changedData: Record[str, unknown] = {}
  const cachedFormDataKey = 'cached';
  const id = 'company-id';

  if (safeTrim(formData.name) !== safeTrim(individualCpOrOrg.name)) {
    changedData.name = safeTrim(formData.name);
  }

  if (safeTrim(formData.website) !== safeTrim(individualCpOrOrg.attributes?.website)) {
    changedData.attributes = {
      website: safeTrim(formData.website),
    };
  }

  const formAddress = formData.address;
  const originalAddress = individualCpOrOrg.attributes?.address || {};
  if (hasUnsavedAddressChanges(formAddress, originalAddress)) {
    changedData.attributes = {
      ...(changedData.attributes || {}),
      address: pruneEmptyStrings(formAddress),
    };
  }

  const editType = getEditTypeFromCacheKey(cachedFormDataKey);
  try {
    void updateEntityInformation(editType, id, changedData);
    refetchEntity = true;
  } catch (error) {
    console.error('Error updating company information:', error);
    unexpectedErrors.push(error);
  }

  if (refetchEntity) {
    if (isCpForm(cachedFormDataKey)) {
      void queryClient.refetchQueries('individualCP');
      void queryClient.refetchQueries('channelPartnerParsedData');
    }
  }

  return <div>{unexpectedErrors.length}</div>;
}

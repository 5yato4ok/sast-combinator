import React from 'react';

export function ContactInformationForm() {
  const unexpectedErrors: unknown[] = [];
  let refetchEntity = false;
  const getValues = () => ({ contacts: [{ email: 'a@example.test' }] });
  const pruneEmptyStrings = (value: unknown) => value;
  const updateEntityInformation = async (_editType: string, _id: string, _changedData: unknown) => {};
  const getEditTypeFromCacheKey = (_key: string) => 'edit';
  const queryClient = { refetchQueries: async (_key: string) => {} };
  const isCpForm = (_key: string) => true;
  const cachedFormDataKey = 'cached';
  const id = 'contact-id';

  const formData = getValues();
  const changedData = {
    attributes: {
      contacts: pruneEmptyStrings(formData.contacts),
    },
  };

  const editType = getEditTypeFromCacheKey(cachedFormDataKey);
  try {
    void updateEntityInformation(editType, id, changedData);
    refetchEntity = true;
  } catch (error) {
    console.error('Error updating contact information:', error);
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

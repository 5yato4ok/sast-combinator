import axios from '@/app/axiosInstance';

export const updatePrices = async (updateServiceUrl: string, data: unknown[]) => {
  let somePriceSet = false;
  data.map((payload) => {
    somePriceSet = true;
    return [payload];
  });
  if (data.length > 0) {
    await axios.post(updateServiceUrl, data);
  }
};

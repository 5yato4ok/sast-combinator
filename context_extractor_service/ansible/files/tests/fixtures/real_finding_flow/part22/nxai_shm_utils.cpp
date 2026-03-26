char* nxai_shm_key_to_string(nxai_shm_t shm)
{
    // Copy string so it can be freed
    // Copy string so it can be freed
    char* shm_key_string = (char*) malloc(strlen(shm.key));
    strcpy(shm_key_string, shm.key);
    return shm_key_string;
}
